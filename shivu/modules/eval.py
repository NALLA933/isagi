import sys
import io
import os
import subprocess
import tempfile
import re
from pyrogram import filters
from shivu import shivuu as app

OWNER_IDS = [8420981179, 5147822244]

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

async def run_code(language, code, message):
    if language not in LANGUAGE_CONFIG:
        return f"Unsupported language: {language}\nSupported: {', '.join(set(LANGUAGE_CONFIG.keys()))}"
    
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
            return "Error: Code execution timed out (30 seconds limit)"
        except FileNotFoundError:
            return f"Error: {language} compiler/interpreter not installed on the server"
        except Exception as e:
            return f"Execution Error: {str(e)}"

@app.on_message(filters.command("run", prefixes="/"))
async def run_command(_, message):
    user_id = message.from_user.id
    
    if user_id not in OWNER_IDS:
        await message.reply_text("You are not authorized to use this command.")
        return
    
    parts = message.text.split(None, 2)
    
    if len(parts) < 2:
        await message.reply_text(
            "Usage:\n"
            "/run <language> <code>\n"
            "or\n"
            "/run <code> (auto-detect)\n\n"
            f"Supported languages: {', '.join(set(LANGUAGE_CONFIG.keys()))}"
        )
        return
    
    if len(parts) == 2:
        language = detect_language(parts[1])
        code = parts[1]
    else:
        language = parts[1].lower()
        code = parts[2]
    
    status_msg = await message.reply_text(f"Running {language} code...")
    
    output = await run_code(language, code, message)
    
    final_output = f"**Language:** {language}\n\n**Output:**\n```\n{output}\n```"
    
    if len(final_output) > 4095:
        with io.BytesIO(output.encode()) as out_file:
            out_file.name = f"output_{language}.txt"
            await app.send_document(
                message.chat.id, 
                document=out_file, 
                caption=f"Language: {language}\n\nOutput was too long, sent as file."
            )
        await status_msg.delete()
    else:
        await status_msg.edit_text(final_output)

async def aexec(code, message):
    exec(f"async def __aexec(message): " + "".join(f"\n {l}" for l in code.split("\n")))
    return await locals()["__aexec"](message)

@app.on_message(filters.command("eval", prefixes="."))
async def evals(_, message):
    user_id = message.from_user.id
    
    if user_id not in OWNER_IDS:
        await message.reply_text("You are not authorized to use this command.")
        return
    
    parts = message.text.split(" ", maxsplit=1)
    if len(parts) < 2:
        await message.reply_text("No code provided to evaluate.")
        return
    
    to_eval = parts[1]
    
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
        final_output = f"```eval\n{stdout.strip()}\n```"
        if len(final_output) > 4095:
            with io.BytesIO(str.encode(stdout)) as out_file:
                out_file.name = "eval.txt"
                await app.send_document(message.chat.id, document=out_file, caption=to_eval)
        else:
            await message.reply_text(final_output)
    else:
        await message.reply_text("No output.")