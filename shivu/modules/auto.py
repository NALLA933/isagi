import io
import base64
import re
import asyncio
import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, List, Tuple
import aiohttp
from pymongo import ReturnDocument
from telegram import Update, InputFile
from telegram.ext import MessageHandler, filters, ContextTypes
from PIL import Image, ImageFilter, ImageStat, ImageEnhance, ImageChops
import numpy as np
from shivu import application, collection, db, CHARA_CHANNEL_ID

AUTHORIZED_USER = 5147822244

class RarityLevel(Enum):
    RARE = (2, "🟣 Rare")
    LEGENDARY = (3, "🟡 Legendary")
    SPECIAL = (4, "💮 Special Edition")
    NEON = (5, "💫 Neon")
    MANGA = (6, "✨ Manga")
    CELESTIAL = (8, "🎐 Celestial")
    PREMIUM = (9, "🔮 Premium")
    MYTHIC = (17, "🏵 Mythic")

    def __init__(self, level: int, display: str):
        self._level, self._display = level, display

    @property
    def level(self) -> int: return self._level
    
    @property
    def display_name(self) -> str: return self._display
    
    @property
    def emoji(self) -> str: return self._display.split()[0]

@dataclass
class DetailedQuality:
    """Comprehensive image quality metrics"""
    # Core metrics
    sharpness: float = 0.0
    contrast: float = 0.0
    brightness: float = 0.0
    resolution: float = 0.0
    
    # Advanced metrics
    color_richness: float = 0.0
    color_balance: float = 0.0
    saturation: float = 0.0
    noise_level: float = 0.0
    blur_detection: float = 0.0
    
    # Detail metrics
    edge_density: float = 0.0
    texture_complexity: float = 0.0
    dynamic_range: float = 0.0
    
    # Composition
    aspect_ratio_score: float = 0.0
    centering: float = 0.0
    
    # Final scores
    overall: float = 0.5
    rarity_level: int = 2
    
    def calculate_overall(self):
        """Calculate weighted overall quality score"""
        self.overall = (
            self.sharpness * 0.18 +
            self.contrast * 0.15 +
            self.brightness * 0.10 +
            self.resolution * 0.15 +
            self.color_richness * 0.10 +
            self.edge_density * 0.08 +
            self.texture_complexity * 0.08 +
            (1 - self.noise_level) * 0.06 +
            (1 - self.blur_detection) * 0.05 +
            self.dynamic_range * 0.05
        )
        return self.overall

    def calculate_rarity(self):
        """Map quality to rarity with precise thresholds"""
        s = self.overall
        
        # Consider both overall and key metrics
        critical_threshold = min(self.sharpness, self.resolution) * 0.3 + s * 0.7
        
        if critical_threshold >= 0.90:
            self.rarity_level = 17  # Mythic
        elif critical_threshold >= 0.82:
            self.rarity_level = 9   # Premium
        elif critical_threshold >= 0.72:
            self.rarity_level = 8   # Celestial
        elif critical_threshold >= 0.62:
            self.rarity_level = 6   # Manga
        elif critical_threshold >= 0.52:
            self.rarity_level = 5   # Neon
        elif critical_threshold >= 0.42:
            self.rarity_level = 4   # Special
        elif critical_threshold >= 0.32:
            self.rarity_level = 3   # Legendary
        else:
            self.rarity_level = 2   # Rare
            
        return self.rarity_level

class AdvancedQualityAnalyzer:
    """Deep image quality analysis with computer vision techniques"""
    
    @staticmethod
    def analyze(img_bytes: bytes) -> DetailedQuality:
        try:
            img = Image.open(io.BytesIO(img_bytes))
            original_mode = img.mode
            
            # Convert to RGB
            if img.mode == 'RGBA':
                bg = Image.new('RGB', img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            quality = DetailedQuality()
            width, height = img.size
            
            # Convert to numpy for advanced analysis
            img_array = np.array(img)
            
            # === SHARPNESS ANALYSIS ===
            gray = img.convert('L')
            gray_array = np.array(gray)
            
            # Laplacian variance (industry standard)
            laplacian = np.array([
                [0, 1, 0],
                [1, -4, 1],
                [0, 1, 0]
            ])
            
            # Apply convolution manually
            laplacian_var = 0
            for i in range(1, gray_array.shape[0] - 1):
                for j in range(1, gray_array.shape[1] - 1):
                    window = gray_array[i-1:i+2, j-1:j+2]
                    conv = np.sum(window * laplacian)
                    laplacian_var += conv ** 2
            
            laplacian_var = laplacian_var / (gray_array.shape[0] * gray_array.shape[1])
            quality.sharpness = min(laplacian_var / 1500, 1.0)
            
            # Edge-based sharpness
            edges = gray.filter(ImageFilter.FIND_EDGES)
            edge_stat = ImageStat.Stat(edges)
            edge_sharpness = min(edge_stat.var[0] / 12000, 1.0)
            quality.sharpness = (quality.sharpness + edge_sharpness) / 2
            
            # === CONTRAST ANALYSIS ===
            gray_stat = ImageStat.Stat(gray)
            rms_contrast = gray_stat.stddev[0]
            quality.contrast = min(rms_contrast / 75, 1.0)
            
            # Michelson contrast
            min_lum = gray_stat.extrema[0][0]
            max_lum = gray_stat.extrema[0][1]
            if max_lum + min_lum > 0:
                michelson = (max_lum - min_lum) / (max_lum + min_lum)
                quality.contrast = (quality.contrast + michelson) / 2
            
            # === BRIGHTNESS ANALYSIS ===
            mean_brightness = gray_stat.mean[0]
            # Optimal brightness around 115-135
            brightness_deviation = abs(mean_brightness - 125) / 125
            quality.brightness = 1.0 - min(brightness_deviation, 1.0)
            
            # === RESOLUTION SCORE ===
            pixels = width * height
            megapixels = pixels / 1_000_000
            
            if megapixels >= 2.0:  # 1920x1080+
                quality.resolution = 1.0
            elif megapixels >= 1.5:
                quality.resolution = 0.95
            elif megapixels >= 1.0:
                quality.resolution = 0.90
            elif megapixels >= 0.9:  # 1280x720
                quality.resolution = 0.85
            elif megapixels >= 0.5:
                quality.resolution = 0.75
            elif megapixels >= 0.3:
                quality.resolution = 0.65
            else:
                quality.resolution = 0.50
            
            # Aspect ratio bonus
            aspect = max(width, height) / min(width, height)
            if 1.3 <= aspect <= 1.8:  # Good aspect ratios
                quality.aspect_ratio_score = 1.0
            elif 1.0 <= aspect <= 2.5:
                quality.aspect_ratio_score = 0.8
            else:
                quality.aspect_ratio_score = 0.6
            
            # === COLOR ANALYSIS ===
            stat = ImageStat.Stat(img)
            
            # Color richness (standard deviation across channels)
            color_std = sum(stat.stddev) / 3
            quality.color_richness = min(color_std / 90, 1.0)
            
            # Color balance (how balanced R, G, B are)
            r_mean, g_mean, b_mean = stat.mean
            color_diff = (abs(r_mean - g_mean) + abs(g_mean - b_mean) + abs(b_mean - r_mean)) / 3
            quality.color_balance = 1.0 - min(color_diff / 80, 1.0)
            
            # Saturation
            hsv = img.convert('HSV')
            hsv_stat = ImageStat.Stat(hsv)
            saturation_mean = hsv_stat.mean[1]
            quality.saturation = min(saturation_mean / 200, 1.0)
            
            # === NOISE DETECTION ===
            # Compare original with slightly blurred version
            blurred = img.filter(ImageFilter.GaussianBlur(1))
            diff = ImageChops.difference(img, blurred)
            diff_stat = ImageStat.Stat(diff)
            noise = sum(diff_stat.stddev) / 3
            quality.noise_level = min(noise / 30, 1.0)
            
            # === BLUR DETECTION ===
            # High-pass filter detection
            high_pass = gray.filter(ImageFilter.UnsharpMask(radius=2, percent=150))
            hp_stat = ImageStat.Stat(high_pass)
            blur_score = hp_stat.var[0]
            quality.blur_detection = 1.0 - min(blur_score / 8000, 1.0)
            
            # === EDGE DENSITY ===
            edges_array = np.array(edges)
            edge_pixels = np.count_nonzero(edges_array > 30)
            total_pixels = edges_array.size
            edge_density = edge_pixels / total_pixels
            quality.edge_density = min(edge_density * 15, 1.0)
            
            # === TEXTURE COMPLEXITY ===
            # Local binary patterns approximation
            texture_score = 0
            step = 20
            for i in range(0, gray_array.shape[0] - step, step):
                for j in range(0, gray_array.shape[1] - step, step):
                    patch = gray_array[i:i+step, j:j+step]
                    texture_score += np.std(patch)
            
            avg_texture = texture_score / ((gray_array.shape[0] // step) * (gray_array.shape[1] // step))
            quality.texture_complexity = min(avg_texture / 50, 1.0)
            
            # === DYNAMIC RANGE ===
            # Histogram analysis
            histogram = gray.histogram()
            histogram_array = np.array(histogram)
            
            # Calculate entropy
            histogram_norm = histogram_array / histogram_array.sum()
            histogram_norm = histogram_norm[histogram_norm > 0]
            entropy = -np.sum(histogram_norm * np.log2(histogram_norm))
            quality.dynamic_range = min(entropy / 8, 1.0)
            
            # === CENTERING (subject detection) ===
            # Simple center mass calculation
            center_x, center_y = width // 2, height // 2
            
            # Find brightest regions (likely subject)
            threshold = gray_stat.mean[0]
            bright_y, bright_x = np.where(gray_array > threshold)
            
            if len(bright_x) > 0:
                mass_x = np.mean(bright_x)
                mass_y = np.mean(bright_y)
                
                # Distance from center
                dist_x = abs(mass_x - center_x) / width
                dist_y = abs(mass_y - center_y) / height
                centering_score = 1.0 - (dist_x + dist_y) / 2
                quality.centering = max(0, centering_score)
            else:
                quality.centering = 0.5
            
            # === CALCULATE FINAL SCORES ===
            quality.calculate_overall()
            quality.calculate_rarity()
            
            return quality
            
        except Exception as e:
            print(f"Advanced quality analysis error: {e}")
            import traceback
            traceback.print_exc()
            return DetailedQuality(overall=0.4, rarity_level=2)

class EnhancedAIIdentifier:
    """Multi-engine character identification with smart parsing"""
    
    SAUCENAO_API_KEY = None
    TIMEOUT = aiohttp.ClientTimeout(total=30)
    MAX_RETRIES = 2
    
    @staticmethod
    async def identify(img_bytes: bytes, status_callback=None) -> Dict[str, str]:
        """Identify character using multiple AI services with detailed progress"""
        
        results = []
        
        # Method 1: Trace.moe (best for anime)
        if status_callback:
            await status_callback("🔍 Searching Trace.moe...")
        result = await EnhancedAIIdentifier._trace_moe_enhanced(img_bytes)
        if result['confidence'] > 0:
            results.append(result)
        
        # Method 2: SauceNAO (if available)
        if EnhancedAIIdentifier.SAUCENAO_API_KEY:
            if status_callback:
                await status_callback("🔍 Searching SauceNAO...")
            result = await EnhancedAIIdentifier._saucenao_enhanced(img_bytes)
            if result['confidence'] > 0:
                results.append(result)
        
        # Method 3: ASCII2D
        if status_callback:
            await status_callback("🔍 Searching ASCII2D...")
        result = await EnhancedAIIdentifier._ascii2d_enhanced(img_bytes)
        if result['confidence'] > 0:
            results.append(result)
        
        # Method 4: IQDB
        if status_callback:
            await status_callback("🔍 Searching IQDB...")
        result = await EnhancedAIIdentifier._iqdb_enhanced(img_bytes)
        if result['confidence'] > 0:
            results.append(result)
        
        # Method 5: Google Lens (bonus)
        if status_callback:
            await status_callback("🔍 Searching Google Lens...")
        result = await EnhancedAIIdentifier._google_lens(img_bytes)
        if result['confidence'] > 0:
            results.append(result)
        
        # Analyze all results
        if results:
            return EnhancedAIIdentifier._merge_results(results)
        
        return {
            "name": "Unknown Character",
            "anime": "Unknown Series",
            "confidence": 0.0,
            "source": "none"
        }
    
    @staticmethod
    def _merge_results(results: List[Dict]) -> Dict:
        """Intelligently merge multiple identification results"""
        if not results:
            return {"name": "Unknown Character", "anime": "Unknown Series", "confidence": 0.0}
        
        # Sort by confidence
        results.sort(key=lambda x: x['confidence'], reverse=True)
        
        # If top result has high confidence, use it
        if results[0]['confidence'] >= 0.75:
            return results[0]
        
        # Otherwise, look for consensus
        name_votes = {}
        anime_votes = {}
        
        for r in results:
            name = r['name'].lower().strip()
            anime = r['anime'].lower().strip()
            
            if name != "unknown character":
                name_votes[name] = name_votes.get(name, 0) + r['confidence']
            
            if anime != "unknown series":
                anime_votes[anime] = anime_votes.get(anime, 0) + r['confidence']
        
        # Get most confident name and anime
        best_name = max(name_votes.items(), key=lambda x: x[1])[0] if name_votes else "unknown character"
        best_anime = max(anime_votes.items(), key=lambda x: x[1])[0] if anime_votes else "unknown series"
        
        # Find result with this combination or highest confidence
        for r in results:
            if r['name'].lower() == best_name or r['anime'].lower() == best_anime:
                return {
                    "name": r['name'] if r['name'].lower() == best_name else results[0]['name'],
                    "anime": r['anime'] if r['anime'].lower() == best_anime else results[0]['anime'],
                    "confidence": results[0]['confidence'],
                    "source": f"merged ({len(results)} sources)"
                }
        
        return results[0]
    
    @staticmethod
    async def _trace_moe_enhanced(img_bytes: bytes) -> Dict:
        """Enhanced Trace.moe with better parsing"""
        try:
            # Resize if too large
            img = Image.open(io.BytesIO(img_bytes))
            if max(img.size) > 1000:
                img.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=90)
                img_bytes = buffer.getvalue()
            
            b64 = base64.b64encode(img_bytes).decode()
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.trace.moe/search",
                    json={"image": b64, "cutBorders": True},
                    timeout=EnhancedAIIdentifier.TIMEOUT
                ) as response:
                    if response.status != 200:
                        return {"name": "Unknown", "anime": "Unknown", "confidence": 0.0}
                    
                    data = await response.json()
                    
                    if not data.get('result'):
                        return {"name": "Unknown", "anime": "Unknown", "confidence": 0.0}
                    
                    # Get best matches
                    best_results = [r for r in data['result'][:3] if r.get('similarity', 0) >= 0.60]
                    
                    if not best_results:
                        return {"name": "Unknown", "anime": "Unknown", "confidence": 0.0}
                    
                    top = best_results[0]
                    similarity = top.get('similarity', 0)
                    
                    # Extract anime
                    anilist = top.get('anilist', {})
                    title = anilist.get('title', {})
                    anime = (
                        title.get('english') or
                        title.get('romaji') or
                        title.get('native') or
                        'Unknown Series'
                    )
                    
                    # Extract character from filename
                    filename = top.get('filename', '')
                    char_name = EnhancedAIIdentifier._smart_extract_name(filename, anime)
                    
                    return {
                        "name": char_name,
                        "anime": anime,
                        "confidence": similarity,
                        "source": "trace.moe"
                    }
                    
        except Exception as e:
            print(f"Trace.moe enhanced error: {e}")
            return {"name": "Unknown", "anime": "Unknown", "confidence": 0.0}
    
    @staticmethod
    async def _saucenao_enhanced(img_bytes: bytes) -> Dict:
        """Enhanced SauceNAO with better parsing"""
        if not EnhancedAIIdentifier.SAUCENAO_API_KEY:
            return {"name": "Unknown", "anime": "Unknown", "confidence": 0.0}
        
        try:
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field('file', img_bytes, filename='search.jpg')
                
                async with session.post(
                    "https://saucenao.com/search.php",
                    data=data,
                    params={
                        'output_type': 2,
                        'api_key': EnhancedAIIdentifier.SAUCENAO_API_KEY,
                        'db': 999,
                        'numres': 5
                    },
                    timeout=EnhancedAIIdentifier.TIMEOUT
                ) as response:
                    if response.status != 200:
                        return {"name": "Unknown", "anime": "Unknown", "confidence": 0.0}
                    
                    result = await response.json()
                    
                    for res in result.get('results', []):
                        similarity = float(res.get('header', {}).get('similarity', 0))
                        
                        if similarity < 55:
                            continue
                        
                        data = res.get('data', {})
                        
                        # Extract character
                        char_name = "Unknown Character"
                        
                        if data.get('characters'):
                            chars = data['characters']
                            if isinstance(chars, list) and chars:
                                char_name = chars[0]
                            elif isinstance(chars, str):
                                char_name = chars
                        
                        if char_name == "Unknown Character" and data.get('title'):
                            char_name = data['title']
                        
                        # Extract anime
                        anime = (
                            data.get('source') or
                            data.get('material') or
                            data.get('eng_name') or
                            data.get('jp_name') or
                            'Unknown Series'
                        )
                        
                        # Clean up
                        char_name = EnhancedAIIdentifier._clean_name(char_name)
                        anime = EnhancedAIIdentifier._clean_name(anime)
                        
                        if char_name != "Unknown Character":
                            return {
                                "name": char_name,
                                "anime": anime,
                                "confidence": similarity / 100,
                                "source": "saucenao"
                            }
                    
        except Exception as e:
            print(f"SauceNAO enhanced error: {e}")
        
        return {"name": "Unknown", "anime": "Unknown", "confidence": 0.0}
    
    @staticmethod
    async def _ascii2d_enhanced(img_bytes: bytes) -> Dict:
        """Enhanced ASCII2D with better parsing"""
        try:
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field('file', img_bytes, filename='search.jpg')
                
                async with session.post(
                    "https://ascii2d.net/search/file",
                    data=data,
                    timeout=EnhancedAIIdentifier.TIMEOUT
                ) as response:
                    if response.status != 200:
                        return {"name": "Unknown", "anime": "Unknown", "confidence": 0.0}
                    
                    html = await response.text()
                    
                    # Try multiple patterns
                    patterns = [
                        r'<div class="detail-box"[^>]*>.*?<h6[^>]*>(.*?)</h6>.*?<h6[^>]*>(.*?)</h6>',
                        r'<h6[^>]*class="[^"]*text-xs[^"]*"[^>]*>(.*?)</h6>',
                    ]
                    
                    for pattern in patterns:
                        matches = re.findall(pattern, html, re.DOTALL)
                        
                        for match in matches[:3]:
                            if len(match) >= 2:
                                char_raw, anime_raw = match[0], match[1]
                            else:
                                char_raw = match[0]
                                anime_raw = "Unknown Series"
                            
                            char_name = re.sub(r'<[^>]+>', '', char_raw).strip()
                            anime_name = re.sub(r'<[^>]+>', '', anime_raw).strip()
                            
                            char_name = EnhancedAIIdentifier._clean_name(char_name)
                            anime_name = EnhancedAIIdentifier._clean_name(anime_name)
                            
                            if char_name and len(char_name) > 2:
                                return {
                                    "name": char_name,
                                    "anime": anime_name,
                                    "confidence": 0.70,
                                    "source": "ascii2d"
                                }
                    
        except Exception as e:
            print(f"ASCII2D enhanced error: {e}")
        
        return {"name": "Unknown", "anime": "Unknown", "confidence": 0.0}
    
    @staticmethod
    async def _iqdb_enhanced(img_bytes: bytes) -> Dict:
        """Enhanced IQDB with better parsing"""
        try:
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field('file', img_bytes, filename='search.jpg')
                
                async with session.post(
                    "https://iqdb.org/",
                    data=data,
                    timeout=EnhancedAIIdentifier.TIMEOUT
                ) as response:
                    if response.status != 200:
                        return {"name": "Unknown", "anime": "Unknown", "confidence": 0.0}
                    
                    html = await response.text()
                    
                    if 'No relevant matches' in html:
                        return {"name": "Unknown", "anime": "Unknown", "confidence": 0.0}
                    
                    # Multiple parsing attempts
                    patterns = [
                        r'<td[^>]*>([^<]+?)\s+[/｜]\s+([^<]+?)</td>',
                        r'alt=["\']([^"\']+)["\']',
                        r'<td>([^<]{5,100})</td>',
                    ]
                    
                    for pattern in patterns:
                        matches = re.findall(pattern, html)
                        
                        for match in matches:
                            if isinstance(match, tuple) and len(match) >= 2:
                                char = EnhancedAIIdentifier._clean_name(match[0])
                                anime = EnhancedAIIdentifier._clean_name(match[1])
                                
                                if char and anime:
                                    return {
                                        "name": char,
                                        "anime": anime,
                                        "confidence": 0.65,
                                        "source": "iqdb"
                                    }
                            elif isinstance(match, str):
                                text = EnhancedAIIdentifier._clean_name(match)
                                if '/' in text or '｜' in text:
                                    parts = re.split(r'[/｜]', text)
                                    if len(parts) >= 2:
                                        return {
                                            "name": parts[1].strip(),
                                            "anime": parts[0].strip(),
                                            "confidence": 0.60,
                                            "source": "iqdb"
                                        }
                    
        except Exception as e:
            print(f"IQDB enhanced error: {e}")
        
        return {"name": "Unknown", "anime": "Unknown", "confidence": 0.0}
    
    @staticmethod
    async def _google_lens(img_bytes: bytes) -> Dict:
        """Experimental Google Lens-style search"""
        try:
            # This is a placeholder - Google Lens API is not publicly available
            # You could integrate with Google Cloud Vision API if needed
            return {"name": "Unknown", "anime": "Unknown", "confidence": 0.0}
        except:
            return {"name": "Unknown", "anime": "Unknown", "confidence": 0.0}
    
    @staticmethod
    def _smart_extract_name(filename: str, anime: str = "") -> str:
        """Intelligently extract character name from filename"""
        if not filename:
            return "Unknown Character"
        
        # Remove extension
        name = re.sub(r'\.[^.]+$', '', filename)
        
        # Remove common patterns
        name = re.sub(r'\[.*?\]', '', name)
        name = re.sub(r'\(.*?\)', '', name)
        name = re.sub(r'[_\-\.]', ' ', name)
        name = re.sub(r'\d{3,}', '', name)
        name = re.sub(r'(?i)(episode|ep|e\d+|s\d+)', '', name)
        
        # Remove anime name from filename if present
        if anime:
            anime_clean = re.sub(r'[^\w\s]', '', anime.lower())
            name_lower = name.lower()
            for word in anime_clean.split():
                if len(word) > 3:
                    name_lower = name_lower.replace(word, '')
            name = name_lower
        
        # Clean up
        name = re.sub(r'\s+', ' ', name).strip()
        
        # Capitalize properly
        words = [w.capitalize() for w in name.split() if len(w) > 1]
        result = ' '.join(words[:4])
        
        return result if len(result) > 2 else "Unknown Character"
    
    @staticmethod
    def _clean_name(text: str) -> str:
        """Clean and normalize names"""
        if not text:
            return ""
        
        # Remove HTML
        text = re.sub(r'<[^>]+>', '', text)
        
        # Remove special markers
        text = re.sub(r'[\[\](){}]', '', text)
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Capitalize
        words = [w.capitalize() for w in text.split() if w]
        
        return ' '.join(words)

class SequenceGen:
    @staticmethod
    async def get_next_id() -> str:
        doc = await db.sequences.find_one_and_update(
            {'_id': 'character_id'},
            {'$inc': {'sequence_value': 1}},
            return_document=ReturnDocument.AFTER,
            upsert=True
        )
        seq = doc.get('sequence_value', 0)
        return str(seq).zfill(4)

class Uploader:
    @staticmethod
    async def upload_to_catbox(file_bytes: bytes, filename: str) -> Optional[str]:
        """Upload to Catbox with retries"""
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession() as session:
                    data = aiohttp.FormData()
                    data.add_field('reqtype', 'fileupload')
                    data.add_field('fileToUpload', file_bytes, filename=filename)
                    
                    async with session.post(
                        "https://catbox.moe/user/api.php",
                        data=data,
                        timeout=aiohttp.ClientTimeout(total=60)
                    ) as response:
                        if response.status == 200:
                            url = (await response.text()).strip()
                            if url.startswith('http'):
                                return url
                
                # Wait before retry
                if attempt < 2:
                    await asyncio.sleep(2)
                    
            except Exception as e:
                print(f"Catbox upload attempt {attempt + 1} failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(2)
        
        return None

    @staticmethod
    async def send_to_channel(char_data: Dict, file_bytes: bytes, context):
        """Send character to Telegram channel"""
        try:
            # Build detailed caption
            quality_bar = "█" * int(char_data["quality_score"] * 10) + "░" * (10 - int(char_data["quality_score"] * 10))
            confidence_bar = "█" * int(char_data["ai_confidence"] * 10) + "░" * (10 - int(char_data["ai_confidence"] * 10))
            
            caption = (
                f'╔══════════════════════╗\n'
                f'  <b>🆔 ID:</b> <code>{char_data["id"]}</code>\n'
                f'╚══════════════════════╝\n\n'
                f'<b>👤 Character:</b> {char_data["name"]}\n'
                f'<b>📺 Anime:</b> {char_data["anime"]}\n\n'
                f'<b>{char_data["rarity_emoji"]} Rarity:</b> {char_data["rarity_name"]}\n\n'
                f'<b>⭐ Quality Score:</b> {char_data["quality_score"]:.2f}/1.00\n'
                f'<code>{quality_bar}</code>\n\n'
                f'<b>🤖 AI Confidence:</b> {char_data["ai_confidence"]:.0%}\n'
                f'<code>{confidence_bar}</code>\n'
                f'<b>🔍 Source:</b> {char_data["ai_source"]}\n\n'
                f'<b>📊 Detailed Metrics:</b>\n'
                f'├ Sharpness: {char_data["metrics"]["sharpness"]:.2f}\n'
                f'├ Contrast: {char_data["metrics"]["contrast"]:.2f}\n'
                f'├ Resolution: {char_data["metrics"]["resolution"]:.2f}\n'
                f'├ Color: {char_data["metrics"]["color_richness"]:.2f}\n'
                f'└ Edge Density: {char_data["metrics"]["edge_density"]:.2f}\n\n'
                f'<i>🚀 Auto-uploaded by</i> '
                f'<a href="tg://user?id={char_data["uploader_id"]}">{char_data["uploader_name"]}</a>'
            )

            file_obj = io.BytesIO(file_bytes)
            file_obj.name = f"{char_data['id']}.jpg"
            
            msg = await context.bot.send_photo(
                chat_id=CHARA_CHANNEL_ID,
                photo=InputFile(file_obj),
                caption=caption,
                parse_mode='HTML'
            )
            
            return msg
            
        except Exception as e:
            print(f"Channel send error: {e}")
            return None

async def auto_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main handler with comprehensive analysis"""
    status_msg = None
    
    try:
        # Security check
        if update.effective_user.id != AUTHORIZED_USER:
            return
        
        if not update.message or not update.message.photo:
            return

        msg = update.message
        status_msg = await msg.reply_text(
            '🔄 <b>Starting Advanced Analysis...</b>',
            parse_mode='HTML'
        )

        # STEP 1: Download
        await status_msg.edit_text(
            '📥 <b>Step 1/6:</b> Downloading image...\n'
            '<i>Getting high-quality version...</i>',
            parse_mode='HTML'
        )
        
        photo = msg.photo[-1]
        file = await photo.get_file()
        file_bytes = bytes(await file.download_as_bytearray())
        file_size = len(file_bytes) / 1024  # KB
        
        await asyncio.sleep(0.5)  # Visual feedback

        # STEP 2: Deep Quality Analysis
        await status_msg.edit_text(
            '📊 <b>Step 2/6:</b> Deep Quality Analysis...\n'
            '<i>Analyzing sharpness, contrast, colors...</i>\n'
            '<i>Computing texture complexity...</i>\n'
            '<i>Detecting blur and noise...</i>',
            parse_mode='HTML'
        )
        
        quality = AdvancedQualityAnalyzer.analyze(file_bytes)
        
        await asyncio.sleep(0.5)

        # STEP 3: AI Character Identification
        async def update_ai_status(status_text):
            try:
                await status_msg.edit_text(
                    f'🤖 <b>Step 3/6:</b> AI Character Identification...\n'
                    f'<i>{status_text}</i>',
                    parse_mode='HTML'
                )
            except:
                pass
        
        await update_ai_status("Initializing AI engines...")
        char_info = await EnhancedAIIdentifier.identify(file_bytes, update_ai_status)
        
        await asyncio.sleep(0.5)

        # STEP 4: Upload to Storage
        await status_msg.edit_text(
            '⬆️ <b>Step 4/6:</b> Uploading to storage...\n'
            '<i>Connecting to Catbox...</i>\n'
            f'<i>File size: {file_size:.1f} KB</i>',
            parse_mode='HTML'
        )
        
        catbox_url = await Uploader.upload_to_catbox(
            file_bytes,
            f"char_{photo.file_unique_id}.jpg"
        )
        
        if not catbox_url:
            await status_msg.edit_text(
                '❌ <b>Upload Failed!</b>\n\n'
                'Could not upload to Catbox storage.\n'
                'Please try again later.',
                parse_mode='HTML'
            )
            return

        # STEP 5: Generate ID & Save to Database
        await status_msg.edit_text(
            '💾 <b>Step 5/6:</b> Saving to database...\n'
            '<i>Generating unique ID...</i>\n'
            '<i>Calculating rarity...</i>',
            parse_mode='HTML'
        )
        
        char_id = await SequenceGen.get_next_id()
        rarity = next(
            (r for r in RarityLevel if r.level == quality.rarity_level),
            RarityLevel.RARE
        )
        
        char_data = {
            'id': char_id,
            'name': char_info['name'],
            'anime': char_info['anime'],
            'rarity': rarity.display_name,
            'rarity_emoji': rarity.emoji,
            'rarity_name': rarity.display_name[2:],
            'img_url': catbox_url,
            'uploader_id': str(update.effective_user.id),
            'uploader_name': update.effective_user.first_name,
            
            # Quality scores
            'quality_score': round(quality.overall, 2),
            'metrics': {
                'sharpness': round(quality.sharpness, 2),
                'contrast': round(quality.contrast, 2),
                'brightness': round(quality.brightness, 2),
                'resolution': round(quality.resolution, 2),
                'color_richness': round(quality.color_richness, 2),
                'edge_density': round(quality.edge_density, 2),
                'texture_complexity': round(quality.texture_complexity, 2),
                'noise_level': round(quality.noise_level, 2),
                'blur_detection': round(quality.blur_detection, 2),
            },
            
            # AI info
            'ai_confidence': round(char_info.get('confidence', 0.0), 2),
            'ai_source': char_info.get('source', 'unknown'),
            
            # Metadata
            'file_size_kb': round(file_size, 1),
            'auto_uploaded': True,
            'upload_timestamp': asyncio.get_event_loop().time()
        }

        # STEP 6: Publish to Channel
        await status_msg.edit_text(
            '📢 <b>Step 6/6:</b> Publishing to channel...\n'
            '<i>Creating announcement...</i>\n'
            '<i>Uploading to Telegram...</i>',
            parse_mode='HTML'
        )
        
        channel_msg = await Uploader.send_to_channel(char_data, file_bytes, context)
        
        if channel_msg and channel_msg.photo:
            char_data['message_id'] = channel_msg.message_id
            char_data['file_id'] = channel_msg.photo[-1].file_id

        # Save to database
        await collection.insert_one(char_data)

        # SUCCESS MESSAGE
        quality_stars = "⭐" * min(5, int(quality.overall * 5))
        confidence_emoji = "🟢" if char_info.get('confidence', 0) > 0.7 else "🟡" if char_info.get('confidence', 0) > 0.5 else "🟠"
        
        success_text = (
            f'✅ <b>Upload Complete!</b>\n\n'
            f'╔═══════════════════════╗\n'
            f'  <b>🆔 Character ID:</b> <code>{char_id}</code>\n'
            f'╚═══════════════════════╝\n\n'
            f'<b>📝 Character Details:</b>\n'
            f'├ 👤 Name: {char_info["name"]}\n'
            f'├ 📺 Anime: {char_info["anime"]}\n'
            f'└ {rarity.emoji} Rarity: {rarity.display_name[2:]}\n\n'
            f'<b>📊 Quality Analysis:</b>\n'
            f'├ Overall: {quality.overall:.2f}/1.00 {quality_stars}\n'
            f'├ Sharpness: {quality.sharpness:.2f}\n'
            f'├ Contrast: {quality.contrast:.2f}\n'
            f'├ Resolution: {quality.resolution:.2f}\n'
            f'├ Color Quality: {quality.color_richness:.2f}\n'
            f'└ Edge Density: {quality.edge_density:.2f}\n\n'
            f'<b>🤖 AI Identification:</b>\n'
            f'├ {confidence_emoji} Confidence: {char_info.get("confidence", 0):.0%}\n'
            f'├ 🔍 Source: {char_info.get("source", "unknown")}\n'
            f'└ 📏 File Size: {file_size:.1f} KB\n\n'
            f'<i>Character has been added to the collection!</i>'
        )
        
        await status_msg.edit_text(success_text, parse_mode='HTML')

    except Exception as e:
        error_msg = (
            f'❌ <b>Error Occurred!</b>\n\n'
            f'<b>Error Type:</b> {type(e).__name__}\n'
            f'<b>Details:</b> <code>{str(e)[:200]}</code>\n\n'
            f'<i>Please try again or contact support.</i>'
        )
        
        print(f"Auto-upload error: {e}")
        import traceback
        traceback.print_exc()
        
        try:
            if status_msg:
                await status_msg.edit_text(error_msg, parse_mode='HTML')
            else:
                await update.message.reply_text(error_msg, parse_mode='HTML')
        except:
            pass

# Register handler
application.add_handler(
    MessageHandler(
        filters.PHOTO & filters.User(user_id=AUTHORIZED_USER),
        auto_upload_handler
    )
)