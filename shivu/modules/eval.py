import sys
import io
import os
import subprocess
import tempfile
import re
import asyncio
import shlex
from datetime import datetime
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from shivu import shivuu as app

OWNER_IDS = [8420981179, 5147822244]

terminal_sessions = {}

LANGUAGE_CONFIG = {
    'python': {'ext': '.py', 'cmd': ['python3', '{file}']},
    'python3': {'ext': '.py', 'cmd': ['python3', '{file}']},
    'py': {'ext': '.py', 'cmd': ['python3', '{file}']},
    'javascript': {'ext': '.js', 'cmd': ['node', '{file}']},
    'js': {'ext': '.js', 'cmd': ['node', '{file}']},
    'node': {'ext': '.js', 'cmd': ['node', '{file}']},
    'c': {'ext': '.c', 'cmd': ['gcc', '{file}', '-o', '{output}'], 'run': ['{output}']},
    'cpp': {'ext': '.cpp', 'cmd': ['g++', '{file}', '-o', '{output}'], 'run': ['{output}']},
    'c++': {'ext': '.cpp', 'cmd': ['g++', '{file}', '-o', '{output}'], 'run': ['{output}']},
    'java': {'ext': '.java', 'cmd': ['javac', '{file}'], 'run': ['java', '-cp', '{dir}', '{classname}']},
    'go': {'ext': '.go', 'cmd': ['go', 'run', '{file}']},
    'golang': {'ext': '.go', 'cmd': ['go', 'run', '{file}']},
    'rust': {'ext': '.rs', 'cmd': ['rustc', '{file}', '-o', '{output}'], 'run': ['{output}']},
    'rs': {'ext': '.rs', 'cmd': ['rustc', '{file}', '-o', '{output}'], 'run': ['{output}']},
    'ruby': {'ext': '.rb', 'cmd': ['ruby', '{file}']},
    'rb': {'ext': '.rb', 'cmd': ['ruby', '{file}']},
    'php': {'ext': '.php', 'cmd': ['php', '{file}']},
    'bash': {'ext': '.sh', 'cmd': ['bash', '{file}']},
    'sh': {'ext': '.sh', 'cmd': ['bash', '{file}']},
    'shell': {'ext': '.sh', 'cmd': ['bash', '{file}']},
    'perl': {'ext': '.pl', 'cmd': ['perl', '{file}']},
    'pl': {'ext': '.pl', 'cmd': ['perl', '{file}']},
    'r': {'ext': '.r', 'cmd': ['Rscript', '{file}']},
    'lua': {'ext': '.lua', 'cmd': ['lua', '{file}']},
    'swift': {'ext': '.swift', 'cmd': ['swift', '{file}']},
    'kotlin': {'ext': '.kt', 'cmd': ['kotlinc', '{file}', '-include-runtime', '-d', '{output}.jar'], 'run': ['java', '-jar', '{output}.jar']},
    'kt': {'ext': '.kt', 'cmd': ['kotlinc', '{file}', '-include-runtime', '-d', '{output}.jar'], 'run': ['java', '-jar', '{output}.jar']},
    'typescript': {'ext': '.ts', 'cmd': ['ts-node', '{file}']},
    'ts': {'ext': '.ts', 'cmd': ['ts-node', '{file}']},
    'dart': {'ext': '.dart', 'cmd': ['dart', '{file}']},
    'scala': {'ext': '.scala', 'cmd': ['scala', '{file}']},
    'haskell': {'ext': '.hs', 'cmd': ['runhaskell', '{file}']},
    'hs': {'ext': '.hs', 'cmd': ['runhaskell', '{file}']},
}

class TerminalSession:
    def __init__(self, user_id):
        self.user_id = user_id
        self.cwd = os.path.expanduser("~")
        self.env = os.environ.copy()
        self.history = []
        self.last_command = None
        self.created_at = datetime.now()
        
    def execute_command(self, command):
        self.history.append(command)
        self.last_command = command
        
        if command.strip().startswith('cd '):
            return self._change_directory(command)
        
        if command.strip().startswith('export '):
            return self._set_env_var(command)
        
        if command.strip() == 'pwd':
            return self.cwd
        
        if command.strip() in ['clear', 'reset']:
            return "Terminal cleared (history preserved)"
        
        if command.strip() == 'history':
            return self._show_history()
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self.cwd,
                env=self.env
            )
            
            output = result.stdout
            if result.stderr:
                output += result.stderr
            
            if result.returncode != 0 and not output:
                output = f"Command exited with code {result.returncode}"
            
            return output if output.strip() else "Command executed successfully (no output)"
            
        except subprocess.TimeoutExpired:
            return "Error: Command timed out (60 seconds limit)"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def _change_directory(self, command):
        try:
            parts = shlex.split(command)
            if len(parts) < 2:
                path = os.path.expanduser("~")
            else:
                path = parts[1]
            
            if not os.path.isabs(path):
                path = os.path.join(self.cwd, path)
            
            path = os.path.normpath(path)
            
            if os.path.isdir(path):
                self.cwd = path
                return f"Changed directory to: {self.cwd}"
            else:
                return f"cd: no such directory: {path}"
        except Exception as e:
            return f"cd: {str(e)}"
    
    def _set_env_var(self, command):
        try:
            match = re.search(r'export\s+([A-Za-z_][A-Za-z0-9_]*)=(.+)', command)
            if match:
                var_name = match.group(1)
                var_value = match.group(2).strip('"').strip("'")
                self.env[var_name] = var_value
                return f"Set {var_name}={var_value}"
            else:
                return "Usage: export VAR=value"
        except Exception as e:
            return f"export: {str(e)}"
    
    def _show_history(self):
        if not self.history:
            return "No command history"
        
        output = "Command History:\n"
        for i, cmd in enumerate(self.history[-50:], 1):
            output += f"{i}. {cmd}\n"
        return output
    
    def get_prompt(self):
        username = os.environ.get('USER', 'user')
        hostname = os.environ.get('HOSTNAME', 'telegram')
        short_cwd = self.cwd.replace(os.path.expanduser("~"), "~")
        return f"{username}@{hostname}:{short_cwd}$"


def get_or_create_session(user_id):
    if user_id not in terminal_sessions:
        terminal_sessions[user_id] = TerminalSession(user_id)
    return terminal_sessions[user_id]


def detect_language(code):
    code_lower = code.lower().strip()
    
    if code.startswith('#include') or code.startswith('int main'):
        if '<<' in code or 'std::' in code or 'cout' in code:
            return 'cpp'
        return 'c'
    
    if 'def ' in code and ('import' in code or code.startswith('print') or ':' in code):
        return 'python'
    
    if ('console.log' in code or 'function' in code or 'const ' in code or 
        'let ' in code or 'var ' in code or '=>' in code):
        return 'javascript'
    
    if 'public class' in code or 'public static void main' in code:
        return 'java'
    
    if 'package main' in code or 'func main()' in code:
        return 'go'
    
    if 'fn main()' in code or 'println!' in code:
        return 'rust'
    
    if 'puts ' in code or 'def ' in code and 'end' in code:
        return 'ruby'
    
    if '<?php' in code or '$' in code and 'echo' in code:
        return 'php'
    
    if code.startswith('#!/bin/bash') or code.startswith('#!/bin/sh'):
        return 'bash'
    
    return 'python'


async def run_code(language, code):
    if language not in LANGUAGE_CONFIG:
        return f"Unsupported language: {language}"
    
    config = LANGUAGE_CONFIG[language]
    
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, f"code{config['ext']}")
        output_path = os.path.join(tmpdir, "output")
        
        with open(file_path, 'w') as f:
            f.write(code)
        
        try:
            cmd = [c.format(
                file=file_path,
                output=output_path,
                dir=tmpdir,
                classname='code'
            ) for c in config['cmd']]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=tmpdir
            )
            
            if 'run' in config:
                if result.returncode != 0:
                    return f"Compilation Error:\n{result.stderr}"
                
                run_cmd = [c.format(
                    output=output_path,
                    dir=tmpdir,
                    classname='code'
                ) for c in config['run']]
                
                result = subprocess.run(
                    run_cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=tmpdir
                )
            
            output = result.stdout
            if result.stderr:
                output += f"\n\nErrors/Warnings:\n{result.stderr}"
            
            if result.returncode != 0:
                output = f"Exit Code: {result.returncode}\n{output}"
            
            return output if output.strip() else "No output."
        
        except subprocess.TimeoutExpired:
            return "Error: Code execution timed out (30 seconds)"
        except FileNotFoundError:
            return f"Error: {language} compiler/interpreter not installed"
        except Exception as e:
            return f"Execution Error: {str(e)}"


@app.on_message(filters.command(["sh", "cmd", "terminal", "term", "$"], prefixes=["#", "+", "@", '"', "-", ";", "!", "'", "/"]) | filters.regex(r"^(sh|cmd|terminal|term)\s+"))
async def execute_terminal_command(_, message):
    user_id = message.from_user.id
    
    if user_id not in OWNER_IDS:
        return
    
    text = message.text.strip()
    
    text = re.sub(r'@\w+', '', text).strip()
    
    if text.startswith(('#', '+', '@', '"', '-', ';', '!', "'", '/')):
        parts = text[1:].strip().split(None, 1)
        if len(parts) < 2:
            return
        command = parts[1]
    else:
        parts = text.split(None, 1)
        if len(parts) < 2:
            return
        command = parts[1]
    
    session = get_or_create_session(user_id)
    
    output = session.execute_command(command)
    
    prompt = session.get_prompt()
    
    if len(output) > 3800:
        with io.BytesIO(output.encode()) as out_file:
            out_file.name = "output.txt"
            await app.send_document(
                message.chat.id,
                document=out_file,
                caption=f"```\n{prompt} {command}\n```\nDirectory: {session.cwd}"
            )
    else:
        final_output = f"```\n{prompt} {command}\n{output}\n```"
        await message.reply_text(final_output)


async def aexec(code, message):
    exec(f"async def __aexec(message): " + "".join(f"\n {l}" for l in code.split("\n")))
    return await locals()["__aexec"](message)


@app.on_message(filters.command(["eval", "run", "exec", "py", "python"], prefixes=["#", "+", "@", '"', "-", ";", "!", "'", "/"]) | filters.regex(r"^(eval|run|exec|py|python)\s+"))
async def evals(_, message):
    user_id = message.from_user.id
    
    if user_id not in OWNER_IDS:
        return
    
    text = message.text.strip()
    
    text = re.sub(r'@\w+', '', text).strip()
    
    if text.startswith(('#', '+', '@', '"', '-', ';', '!', "'", '/')):
        parts = text[1:].strip().split(None, 1)
    else:
        parts = text.split(None, 1)
    
    if len(parts) < 2:
        return
    
    command_word = parts[0].lower()
    code_or_lang = parts[1]
    
    if command_word in ['run']:
        code_parts = code_or_lang.split(None, 1)
        if len(code_parts) == 2 and code_parts[0].lower() in LANGUAGE_CONFIG:
            language = code_parts[0].lower()
            code = code_parts[1]
        else:
            language = detect_language(code_or_lang)
            code = code_or_lang
        
        output = await run_code(language, code)
        
        if len(output) > 3800:
            with io.BytesIO(output.encode()) as out_file:
                out_file.name = f"output_{language}.txt"
                await app.send_document(
                    message.chat.id,
                    document=out_file,
                    caption=f"Language: {language}"
                )
        else:
            final_output = f"Language: {language}\n\n```\n{output}\n```"
            await message.reply_text(final_output)
    
    else:
        to_eval = code_or_lang
        
        old_stdout = sys.stdout
        redirected_output = sys.stdout = io.StringIO()
        stdout = None
        
        try:
            await aexec(to_eval, message)
            stdout = redirected_output.getvalue()
        except Exception as e:
            stdout = f"Exception occurred: {e}"
        finally:
            sys.stdout = old_stdout
        
        if stdout:
            if len(stdout) > 3800:
                with io.BytesIO(str.encode(stdout)) as out_file:
                    out_file.name = "eval.txt"
                    await app.send_document(message.chat.id, document=out_file, caption="Python Eval Output")
            else:
                final_output = f"```python\n{stdout.strip()}\n```"
                await message.reply_text(final_output)
        else:
            await message.reply_text("```\nNo output\n```")