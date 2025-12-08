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
class AIDetectionResult:
    """Results from AI/Fake detection"""
    is_authentic: bool = True
    confidence: float = 0.0
    ai_probability: float = 0.0
    detection_method: str = ""
    warning_flags: List[str] = None
    
    def __post_init__(self):
        if self.warning_flags is None:
            self.warning_flags = []

@dataclass
class DetailedQuality:
    """Comprehensive image quality metrics"""
    sharpness: float = 0.0
    contrast: float = 0.0
    brightness: float = 0.0
    resolution: float = 0.0
    color_richness: float = 0.0
    color_balance: float = 0.0
    saturation: float = 0.0
    noise_level: float = 0.0
    blur_detection: float = 0.0
    edge_density: float = 0.0
    texture_complexity: float = 0.0
    dynamic_range: float = 0.0
    aspect_ratio_score: float = 0.0
    centering: float = 0.0
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
        critical_threshold = min(self.sharpness, self.resolution) * 0.3 + s * 0.7
        
        if critical_threshold >= 0.90:
            self.rarity_level = 17
        elif critical_threshold >= 0.82:
            self.rarity_level = 9
        elif critical_threshold >= 0.72:
            self.rarity_level = 8
        elif critical_threshold >= 0.62:
            self.rarity_level = 6
        elif critical_threshold >= 0.52:
            self.rarity_level = 5
        elif critical_threshold >= 0.42:
            self.rarity_level = 4
        elif critical_threshold >= 0.32:
            self.rarity_level = 3
        else:
            self.rarity_level = 2
            
        return self.rarity_level

class AIImageDetector:
    """Advanced AI-generated image detection system"""
    
    @staticmethod
    async def detect_ai_generation(img_bytes: bytes) -> AIDetectionResult:
        """Comprehensive AI detection using multiple methods"""
        result = AIDetectionResult()
        
        try:
            img = Image.open(io.BytesIO(img_bytes))
            if img.mode == 'RGBA':
                bg = Image.new('RGB', img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            img_array = np.array(img)
            
            # Multiple detection methods
            checks = []
            
            # 1. Frequency Domain Analysis
            freq_score = AIImageDetector._frequency_analysis(img_array)
            checks.append(('frequency', freq_score))
            
            # 2. Noise Pattern Detection
            noise_score = AIImageDetector._noise_pattern_analysis(img_array)
            checks.append(('noise', noise_score))
            
            # 3. Color Distribution Analysis
            color_score = AIImageDetector._color_distribution_check(img_array)
            checks.append(('color', color_score))
            
            # 4. Edge Artifacts Detection
            edge_score = AIImageDetector._edge_artifact_detection(img)
            checks.append(('edges', edge_score))
            
            # 5. Texture Consistency
            texture_score = AIImageDetector._texture_consistency(img_array)
            checks.append(('texture', texture_score))
            
            # 6. Metadata Analysis
            metadata_score = AIImageDetector._metadata_analysis(img_bytes)
            checks.append(('metadata', metadata_score))
            
            # 7. Pixel Pattern Analysis
            pixel_score = AIImageDetector._pixel_pattern_check(img_array)
            checks.append(('pixels', pixel_score))
            
            # Aggregate results
            ai_scores = [score for _, score in checks]
            result.ai_probability = sum(ai_scores) / len(ai_scores)
            
            # Determine if authentic
            result.is_authentic = result.ai_probability < 0.65
            result.confidence = abs(result.ai_probability - 0.5) * 2
            
            # Flag suspicious patterns
            for method, score in checks:
                if score > 0.75:
                    result.warning_flags.append(f"High AI signature in {method} ({score:.2f})")
            
            result.detection_method = f"Multi-check ({len(checks)} methods)"
            
            return result
            
        except Exception as e:
            print(f"AI detection error: {e}")
            return AIDetectionResult(is_authentic=True, confidence=0.0)
    
    @staticmethod
    def _frequency_analysis(img_array: np.ndarray) -> float:
        """Detect AI patterns in frequency domain"""
        try:
            gray = np.mean(img_array, axis=2).astype(np.float32)
            
            # Simple DCT-like analysis
            h, w = gray.shape
            block_size = 8
            ai_score = 0.0
            count = 0
            
            for i in range(0, h - block_size, block_size):
                for j in range(0, w - block_size, block_size):
                    block = gray[i:i+block_size, j:j+block_size]
                    freq_var = np.var(np.diff(block, axis=0)) + np.var(np.diff(block, axis=1))
                    
                    # AI images often have suspiciously uniform frequency patterns
                    if freq_var < 5 or freq_var > 1000:
                        ai_score += 1
                    count += 1
            
            return min(ai_score / count * 3, 1.0)
        except:
            return 0.0
    
    @staticmethod
    def _noise_pattern_analysis(img_array: np.ndarray) -> float:
        """Detect unnatural noise patterns"""
        try:
            # AI images often lack natural sensor noise
            r, g, b = img_array[:,:,0], img_array[:,:,1], img_array[:,:,2]
            
            r_noise = np.std(np.diff(r.flatten()))
            g_noise = np.std(np.diff(g.flatten()))
            b_noise = np.std(np.diff(b.flatten()))
            
            avg_noise = (r_noise + g_noise + b_noise) / 3
            
            # Too clean = likely AI (natural photos have noise ~10-30)
            if avg_noise < 5:
                return 0.85
            elif avg_noise < 8:
                return 0.70
            elif avg_noise > 50:
                return 0.60  # Too noisy could also be AI
            else:
                return 0.30
        except:
            return 0.0
    
    @staticmethod
    def _color_distribution_check(img_array: np.ndarray) -> float:
        """Check for unnatural color distributions"""
        try:
            # AI generators sometimes produce unrealistic color distributions
            r_hist = np.histogram(img_array[:,:,0], bins=256, range=(0, 256))[0]
            g_hist = np.histogram(img_array[:,:,1], bins=256, range=(0, 256))[0]
            b_hist = np.histogram(img_array[:,:,2], bins=256, range=(0, 256))[0]
            
            # Check for unusual peaks or gaps
            r_peaks = len([i for i in range(1, 255) if r_hist[i] > r_hist[i-1] and r_hist[i] > r_hist[i+1]])
            g_peaks = len([i for i in range(1, 255) if g_hist[i] > g_hist[i-1] and g_hist[i] > g_hist[i+1]])
            b_peaks = len([i for i in range(1, 255) if b_hist[i] > b_hist[i-1] and b_hist[i] > b_hist[i+1]])
            
            avg_peaks = (r_peaks + g_peaks + b_peaks) / 3
            
            # AI images often have too many or too few peaks
            if avg_peaks < 5 or avg_peaks > 50:
                return 0.75
            else:
                return 0.35
        except:
            return 0.0
    
    @staticmethod
    def _edge_artifact_detection(img: Image.Image) -> float:
        """Detect AI artifacts around edges"""
        try:
            edges = img.filter(ImageFilter.FIND_EDGES)
            edges_array = np.array(edges.convert('L'))
            
            # Check for unnatural edge patterns
            edge_pixels = edges_array > 30
            edge_count = np.sum(edge_pixels)
            
            if edge_count == 0:
                return 0.80  # No edges = likely AI
            
            # Check edge continuity
            total_pixels = edges_array.size
            edge_ratio = edge_count / total_pixels
            
            # AI images often have too perfect or too broken edges
            if edge_ratio < 0.05 or edge_ratio > 0.40:
                return 0.70
            else:
                return 0.30
        except:
            return 0.0
    
    @staticmethod
    def _texture_consistency(img_array: np.ndarray) -> float:
        """Check for unnatural texture consistency"""
        try:
            gray = np.mean(img_array, axis=2)
            h, w = gray.shape
            
            # Divide into regions and check variance
            regions = 16
            region_h = h // 4
            region_w = w // 4
            
            variances = []
            for i in range(4):
                for j in range(4):
                    region = gray[i*region_h:(i+1)*region_h, j*region_w:(j+1)*region_w]
                    variances.append(np.var(region))
            
            var_std = np.std(variances)
            
            # AI images often have too uniform texture variance
            if var_std < 50:
                return 0.75
            elif var_std < 100:
                return 0.55
            else:
                return 0.30
        except:
            return 0.0
    
    @staticmethod
    def _metadata_analysis(img_bytes: bytes) -> float:
        """Check EXIF and metadata for AI signatures"""
        try:
            img = Image.open(io.BytesIO(img_bytes))
            
            # Check for common AI generator signatures
            ai_keywords = [
                'stable diffusion', 'midjourney', 'dall-e', 'dalle',
                'artificial', 'generated', 'ai', 'neural', 'gan',
                'diffusion', 'pytorch', 'tensorflow', 'novelai',
                'waifu', 'pixai', 'niji', 'automatic1111'
            ]
            
            # Check metadata
            info = img.info
            for key, value in info.items():
                if isinstance(value, str):
                    value_lower = value.lower()
                    for keyword in ai_keywords:
                        if keyword in value_lower:
                            return 0.95  # Definite AI signature
            
            # Check software tag
            if hasattr(img, '_getexif') and img._getexif():
                exif = img._getexif()
                software = exif.get(0x0131, '')  # Software tag
                if software:
                    for keyword in ai_keywords:
                        if keyword in software.lower():
                            return 0.95
            
            return 0.20
        except:
            return 0.0
    
    @staticmethod
    def _pixel_pattern_check(img_array: np.ndarray) -> float:
        """Detect repeating pixel patterns common in AI"""
        try:
            # Check for unnatural repetition
            gray = np.mean(img_array, axis=2).astype(np.uint8)
            h, w = gray.shape
            
            # Sample patches and look for duplicates
            patch_size = 16
            patches = []
            
            for i in range(0, min(h - patch_size, 200), patch_size):
                for j in range(0, min(w - patch_size, 200), patch_size):
                    patch = gray[i:i+patch_size, j:j+patch_size]
                    patches.append(patch.tobytes())
            
            # Count unique patches
            unique_patches = len(set(patches))
            total_patches = len(patches)
            
            if total_patches == 0:
                return 0.0
            
            uniqueness_ratio = unique_patches / total_patches
            
            # AI images sometimes have suspicious repetition
            if uniqueness_ratio < 0.70:
                return 0.75
            else:
                return 0.25
        except:
            return 0.0

class MultiAnimeAPI:
    """Multi-source anime character verification"""
    
    JIKAN_BASE = "https://api.jikan.moe/v4"
    ANILIST_BASE = "https://graphql.anilist.co"
    MAL_SEARCH = "https://myanimelist.net/api"
    ANIDB_BASE = "http://api.anidb.net:9001/httpapi"
    
    @staticmethod
    async def verify_character(char_name: str, anime_name: str, status_callback=None) -> Dict:
        """Verify character exists across multiple anime databases"""
        
        results = []
        
        # 1. Search Jikan (MyAnimeList)
        if status_callback:
            await status_callback("🔍 Checking MyAnimeList...")
        result = await MultiAnimeAPI._search_jikan(char_name, anime_name)
        if result['found']:
            results.append(result)
        
        # 2. Search AniList
        if status_callback:
            await status_callback("🔍 Checking AniList...")
        result = await MultiAnimeAPI._search_anilist(char_name, anime_name)
        if result['found']:
            results.append(result)
        
        # 3. Search Anime-Planet
        if status_callback:
            await status_callback("🔍 Checking Anime-Planet...")
        result = await MultiAnimeAPI._search_anime_planet(char_name, anime_name)
        if result['found']:
            results.append(result)
        
        # 4. Search Kitsu
        if status_callback:
            await status_callback("🔍 Checking Kitsu...")
        result = await MultiAnimeAPI._search_kitsu(char_name, anime_name)
        if result['found']:
            results.append(result)
        
        # Aggregate results
        if not results:
            return {
                'verified': False,
                'confidence': 0.0,
                'sources': 0,
                'character_name': char_name,
                'anime_name': anime_name
            }
        
        # Calculate consensus
        total_confidence = sum(r['confidence'] for r in results)
        avg_confidence = total_confidence / len(results)
        
        # Get most reliable character name
        best_result = max(results, key=lambda x: x['confidence'])
        
        return {
            'verified': True,
            'confidence': avg_confidence,
            'sources': len(results),
            'character_name': best_result.get('verified_name', char_name),
            'anime_name': best_result.get('verified_anime', anime_name),
            'character_id': best_result.get('character_id'),
            'anime_id': best_result.get('anime_id'),
            'mal_url': best_result.get('mal_url'),
            'image_url': best_result.get('image_url'),
            'all_sources': [r['source'] for r in results]
        }
    
    @staticmethod
    async def _search_jikan(char_name: str, anime_name: str) -> Dict:
        """Search MyAnimeList via Jikan"""
        try:
            async with aiohttp.ClientSession() as session:
                # Search for character
                async with session.get(
                    f"{MultiAnimeAPI.JIKAN_BASE}/characters",
                    params={'q': char_name, 'limit': 10},
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    if response.status != 200:
                        return {'found': False}
                    
                    data = await response.json()
                    characters = data.get('data', [])
                    
                    # Look for matching anime
                    for char in characters:
                        char_mal_id = char.get('mal_id')
                        char_full_name = char.get('name', '')
                        
                        # Check if name matches
                        if MultiAnimeAPI._name_similarity(char_name, char_full_name) < 0.6:
                            continue
                        
                        # Get character details to check anime
                        await asyncio.sleep(1)  # Rate limit
                        
                        async with session.get(
                            f"{MultiAnimeAPI.JIKAN_BASE}/characters/{char_mal_id}/anime",
                            timeout=aiohttp.ClientTimeout(total=15)
                        ) as char_response:
                            if char_response.status == 200:
                                char_data = await char_response.json()
                                anime_list = char_data.get('data', [])
                                
                                for anime in anime_list:
                                    anime_title = anime.get('anime', {}).get('title', '')
                                    
                                    if MultiAnimeAPI._name_similarity(anime_name, anime_title) > 0.7:
                                        return {
                                            'found': True,
                                            'confidence': 0.95,
                                            'source': 'MyAnimeList',
                                            'verified_name': char_full_name,
                                            'verified_anime': anime_title,
                                            'character_id': char_mal_id,
                                            'anime_id': anime.get('anime', {}).get('mal_id'),
                                            'mal_url': char.get('url'),
                                            'image_url': char.get('images', {}).get('jpg', {}).get('image_url')
                                        }
            
            return {'found': False}
        except Exception as e:
            print(f"Jikan search error: {e}")
            return {'found': False}
    
    @staticmethod
    async def _search_anilist(char_name: str, anime_name: str) -> Dict:
        """Search AniList GraphQL"""
        try:
            query = '''
            query ($search: String) {
              Character(search: $search) {
                id
                name {
                  full
                  native
                }
                image {
                  large
                }
                media(sort: POPULARITY_DESC, type: ANIME) {
                  nodes {
                    id
                    title {
                      romaji
                      english
                      native
                    }
                  }
                }
              }
            }
            '''
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    MultiAnimeAPI.ANILIST_BASE,
                    json={'query': query, 'variables': {'search': char_name}},
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    if response.status != 200:
                        return {'found': False}
                    
                    data = await response.json()
                    char_data = data.get('data', {}).get('Character')
                    
                    if not char_data:
                        return {'found': False}
                    
                    char_full = char_data.get('name', {}).get('full', '')
                    
                    # Check anime matches
                    for media in char_data.get('media', {}).get('nodes', []):
                        titles = media.get('title', {})
                        for title in [titles.get('english'), titles.get('romaji'), titles.get('native')]:
                            if title and MultiAnimeAPI._name_similarity(anime_name, title) > 0.7:
                                return {
                                    'found': True,
                                    'confidence': 0.90,
                                    'source': 'AniList',
                                    'verified_name': char_full,
                                    'verified_anime': title,
                                    'character_id': char_data.get('id'),
                                    'anime_id': media.get('id'),
                                    'image_url': char_data.get('image', {}).get('large')
                                }
            
            return {'found': False}
        except Exception as e:
            print(f"AniList search error: {e}")
            return {'found': False}
    
    @staticmethod
    async def _search_anime_planet(char_name: str, anime_name: str) -> Dict:
        """Search Anime-Planet (web scraping)"""
        try:
            search_url = f"https://www.anime-planet.com/characters/all?name={char_name.replace(' ', '+')}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status != 200:
                        return {'found': False}
                    
                    html = await response.text()
                    
                    # Simple pattern matching
                    if anime_name.lower() in html.lower() and char_name.lower() in html.lower():
                        return {
                            'found': True,
                            'confidence': 0.75,
                            'source': 'Anime-Planet',
                            'verified_name': char_name,
                            'verified_anime': anime_name
                        }
            
            return {'found': False}
        except:
            return {'found': False}
    
    @staticmethod
    async def _search_kitsu(char_name: str, anime_name: str) -> Dict:
        """Search Kitsu API"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://kitsu.io/api/edge/characters",
                    params={'filter[name]': char_name},
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    if response.status != 200:
                        return {'found': False}
                    
                    data = await response.json()
                    
                    for char in data.get('data', []):
                        char_name_api = char.get('attributes', {}).get('name', '')
                        
                        if MultiAnimeAPI._name_similarity(char_name, char_name_api) > 0.7:
                            return {
                                'found': True,
                                'confidence': 0.80,
                                'source': 'Kitsu',
                                'verified_name': char_name_api,
                                'verified_anime': anime_name,
                                'character_id': char.get('id')
                            }
            
            return {'found': False}
        except:
            return {'found': False}
    
    @staticmethod
    def _name_similarity(name1: str, name2: str) -> float:
        """Calculate name similarity score"""
        name1 = name1.lower().strip()
        name2 = name2.lower().strip()
        
        if name1 == name2:
            return 1.0
        
        # Check if one contains the other
        if name1 in name2 or name2 in name1:
            return 0.85
        
        # Simple Levenshtein-like comparison
        words1 = set(name1.split())
        words2 = set(name2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0.0

class AdvancedQualityAnalyzer:
    """Deep image quality analysis"""
    
    @staticmethod
    def analyze(img_bytes: bytes) -> DetailedQuality:
        try:
            img = Image.open(io.BytesIO(img_bytes))
            original_mode = img.mode
            
            if img.mode == 'RGBA':
                bg = Image.new('RGB', img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            quality = DetailedQuality()
            width, height = img.size
            img_array = np.array(img)
            
            # === SHARPNESS ===
            gray = img.convert('L')
            gray_array = np.array(gray)
            
            laplacian = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]])
            laplacian_var = 0
            for i in range(1, gray_array.shape[0] - 1):
                for j in range(1, gray_array.shape[1] - 1):
                    window = gray_array[i-1:i+2, j-1:j+2]
                    conv = np.sum(window * laplacian)
                    laplacian_var += conv ** 2
            
            laplacian_var = laplacian_var / (gray_array.shape[0] * gray_array.shape[1])
            quality.sharpness = min(laplacian_var / 1500, 1.0)
            
            edges = gray.filter(ImageFilter.FIND_EDGES)
            edge_stat = ImageStat.Stat(edges)
            edge_sharpness = min(edge_stat.var[0] / 12000, 1.0)
            quality.sharpness = (quality.sharpness + edge_sharpness) / 2
            
            # === CONTRAST ===
            gray_stat = ImageStat.Stat(gray)
            rms_contrast = gray_stat.stddev[0]
            quality.contrast = min(rms_contrast / 75, 1.0)
            
            # === BRIGHTNESS ===
            mean_brightness = gray_stat.mean[0]
            brightness_deviation = abs(mean_brightness - 125) / 125
            quality.brightness = 1.0 - min(brightness_deviation, 1.0)
            
            # === RESOLUTION ===
            pixels = width * height
            megapixels = pixels / 1_000_000
            
            if megapixels >= 2.0:
                quality.resolution = 1.0
            elif megapixels >= 1.5:
                quality.resolution = 0.95
            elif megapixels >= 1.0:
                quality.resolution = 0.90
            elif megapixels >= 0.9:
                quality.resolution = 0.85
            elif megapixels >= 0.5:
                quality.resolution = 0.75
            elif megapixels >= 0.3:
                quality.resolution = 0.65
            else:
                quality.resolution = 0.50
            
            # === COLOR ANALYSIS ===
            stat = ImageStat.Stat(img)
            color_std = sum(stat.stddev) / 3
            quality.color_richness = min(color_std / 90, 1.0)
            
            r_mean, g_mean, b_mean = stat.mean
            color_diff = (abs(r_mean - g_mean) + abs(g_mean - b_mean) + abs(b_mean - r_mean)) / 3
            quality.color_balance = 1.0 - min(color_diff / 80, 1.0)
            
            # === EDGE DENSITY ===
            edges_array = np.array(edges)
            edge_pixels = np.count_nonzero(edges_array > 30)
            total_pixels = edges_array.size
            edge_density = edge_pixels / total_pixels
            quality.edge_density = min(edge_density * 15, 1.0)
            
            quality.calculate_overall()
            quality.calculate_rarity()
            
            return quality
            
        except Exception as e:
            print(f"Quality analysis error: {e}")
            return DetailedQuality(overall=0.4, rarity_level=2)

class AIVisionIdentifier:
    """Multi-model AI vision identification"""
    
    DEEPINFRA_API_KEY = None  # Set your DeepInfra API key
    
    ENDPOINTS = {
        "vision": [
            {"url": "https://api.deepinfra.com/v1/openai/chat/completions",
             "model": "meta-llama/Llama-3.2-90B-Vision-Instruct"},
            {"url": "https://api.deepinfra.com/v1/openai/chat/completions",
             "model": "meta-llama/Llama-3.2-11B-Vision-Instruct"},
        ],
        "deepseek": [
            {"url": "https://api.deepinfra.com/v1/openai/chat/completions",
             "model": "deepseek-ai/DeepSeek-V3"},
        ],
        "llama": [
            {"url": "https://api.deepinfra.com/v1/openai/chat/completions",
             "model": "meta-llama/Llama-3.3-70B-Instruct"},
            {"url": "https://api.deepinfra.com/v1/openai/chat/completions",
             "model": "meta-llama/Meta-Llama-3.1-405B-Instruct"},
        ],
        "gpt": [
            {"url": "https://api.shuttleai.app/v1/chat/completions",
             "model": "gpt-4o-mini",
             "auth": "Bearer shuttle-free-api-key"},
        ],
        "gemini": [
            {"url": "https://api.shuttleai.app/v1/chat/completions",
             "model": "gemini-1.5-flash",
             "auth": "Bearer shuttle-free-api-key"},
        ],
        "claude": [
            {"url": "https://api.shuttleai.app/v1/chat/completions",
             "model": "claude-3-haiku",
             "auth": "Bearer shuttle-free-api-key"},
        ],
        "qwen": [
            {"url": "https://api.deepinfra.com/v1/openai/chat/completions",
             "model": "Qwen/Qwen2.5-72B-Instruct"},
        ],
        "mixtral": [
            {"url": "https://api.deepinfra.com/v1/openai/chat/completions",
             "model": "mistralai/Mixtral-8x22B-Instruct-v0.1"},
        ],
    }
    
    @staticmethod
    async def identify_with_vision(img_bytes: bytes, status_callback=None) -> Dict:
        """Identify character using AI vision models"""
        
        # Convert image to base64
        b64_image = base64.b64encode(img_bytes).decode('utf-8')
        
        # Prepare prompt
        prompt = """Analyze this anime character image and provide ONLY a JSON response with this exact format:
{
    "character_name": "Full character name",
    "anime_series": "Full anime/manga series name",
    "confidence": 0.95,
    "hair_color": "color",
    "eye_color": "color",
    "distinctive_features": ["feature1", "feature2"],
    "character_role": "main/supporting/minor"
}

Important:
- If you recognize the character, provide accurate information with high confidence (0.8-1.0)
- If unsure, provide best guess with lower confidence (0.3-0.7)
- If completely unknown, set confidence to 0.0
- ONLY return valid JSON, no other text"""

        results = []
        
        # Try vision models first (best for anime)
        if status_callback:
            await status_callback("🤖 Analyzing with Llama Vision 90B...")
        
        for endpoint in AIVisionIdentifier.ENDPOINTS["vision"]:
            result = await AIVisionIdentifier._query_vision_model(
                endpoint, b64_image, prompt
            )
            if result and result.get('confidence', 0) > 0:
                result['source'] = f"vision-{endpoint['model'].split('/')[-1]}"
                results.append(result)
                if result['confidence'] > 0.8:
                    break  # High confidence, no need to continue
        
        # Try other powerful models if needed
        if not results or max(r['confidence'] for r in results) < 0.7:
            if status_callback:
                await status_callback("🤖 Analyzing with GPT-4o-mini...")
            
            for endpoint in AIVisionIdentifier.ENDPOINTS["gpt"]:
                result = await AIVisionIdentifier._query_vision_model(
                    endpoint, b64_image, prompt
                )
                if result and result.get('confidence', 0) > 0:
                    result['source'] = "gpt-4o-mini"
                    results.append(result)
        
        # Try Gemini
        if not results or max(r['confidence'] for r in results) < 0.7:
            if status_callback:
                await status_callback("🤖 Analyzing with Gemini Flash...")
            
            for endpoint in AIVisionIdentifier.ENDPOINTS["gemini"]:
                result = await AIVisionIdentifier._query_vision_model(
                    endpoint, b64_image, prompt
                )
                if result and result.get('confidence', 0) > 0:
                    result['source'] = "gemini-flash"
                    results.append(result)
        
        # Try Claude
        if not results or max(r['confidence'] for r in results) < 0.7:
            if status_callback:
                await status_callback("🤖 Analyzing with Claude Haiku...")
            
            for endpoint in AIVisionIdentifier.ENDPOINTS["claude"]:
                result = await AIVisionIdentifier._query_vision_model(
                    endpoint, b64_image, prompt
                )
                if result and result.get('confidence', 0) > 0:
                    result['source'] = "claude-haiku"
                    results.append(result)
        
        if not results:
            return {
                'name': 'Unknown Character',
                'anime': 'Unknown Series',
                'confidence': 0.0,
                'source': 'ai-vision'
            }
        
        # Merge results
        return AIVisionIdentifier._merge_vision_results(results)
    
    @staticmethod
    async def _query_vision_model(endpoint: Dict, b64_image: str, prompt: str) -> Optional[Dict]:
        """Query a single vision model"""
        try:
            headers = {
                "Content-Type": "application/json",
            }
            
            # Add authentication
            if endpoint.get('auth'):
                headers["Authorization"] = endpoint['auth']
            elif AIVisionIdentifier.DEEPINFRA_API_KEY:
                headers["Authorization"] = f"Bearer {AIVisionIdentifier.DEEPINFRA_API_KEY}"
            
            # Prepare payload
            payload = {
                "model": endpoint['model'],
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64_image}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 500,
                "temperature": 0.3,
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    endpoint['url'],
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        print(f"Vision model error: {response.status}")
                        return None
                    
                    data = await response.json()
                    content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
                    
                    # Extract JSON from response
                    import json
                    
                    # Try to find JSON in the response
                    json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
                    if json_match:
                        result = json.loads(json_match.group())
                        return {
                            'name': result.get('character_name', 'Unknown'),
                            'anime': result.get('anime_series', 'Unknown'),
                            'confidence': float(result.get('confidence', 0.0)),
                            'details': {
                                'hair_color': result.get('hair_color'),
                                'eye_color': result.get('eye_color'),
                                'features': result.get('distinctive_features', []),
                                'role': result.get('character_role')
                            }
                        }
                    
                    return None
                    
        except Exception as e:
            print(f"Vision model query error: {e}")
            return None
    
    @staticmethod
    def _merge_vision_results(results: List[Dict]) -> Dict:
        """Merge results from multiple vision models"""
        if not results:
            return {'name': 'Unknown', 'anime': 'Unknown', 'confidence': 0.0}
        
        # Sort by confidence
        results.sort(key=lambda x: x['confidence'], reverse=True)
        
        # If top result has high confidence, use it
        if results[0]['confidence'] >= 0.8:
            return results[0]
        
        # Otherwise look for consensus
        name_votes = {}
        anime_votes = {}
        
        for r in results:
            name = r['name'].lower().strip()
            anime = r['anime'].lower().strip()
            
            if name != "unknown" and name != "unknown character":
                name_votes[name] = name_votes.get(name, 0) + r['confidence']
            
            if anime != "unknown" and anime != "unknown series":
                anime_votes[anime] = anime_votes.get(anime, 0) + r['confidence']
        
        if name_votes and anime_votes:
            best_name = max(name_votes.items(), key=lambda x: x[1])[0]
            best_anime = max(anime_votes.items(), key=lambda x: x[1])[0]
            
            # Find result matching consensus
            for r in results:
                if r['name'].lower() == best_name or r['anime'].lower() == best_anime:
                    return {
                        'name': r['name'].title() if r['name'].lower() == best_name else results[0]['name'],
                        'anime': r['anime'].title() if r['anime'].lower() == best_anime else results[0]['anime'],
                        'confidence': results[0]['confidence'],
                        'source': f"ai-consensus-{len(results)}",
                        'details': r.get('details', {})
                    }
        
        return results[0]

class EnhancedAIIdentifier:
    """Multi-engine character identification"""
    
    SAUCENAO_API_KEY = None
    TIMEOUT = aiohttp.ClientTimeout(total=30)
    
    @staticmethod
    async def identify(img_bytes: bytes, status_callback=None) -> Dict[str, str]:
        """Identify character using multiple AI services + Vision models"""
        
        results = []
        
        # NEW: AI Vision Models (Most Powerful)
        if status_callback:
            await status_callback("🤖 Analyzing with AI Vision Models...")
        
        vision_result = await AIVisionIdentifier.identify_with_vision(img_bytes, status_callback)
        if vision_result['confidence'] > 0:
            results.append(vision_result)
        
        # Method 1: Trace.moe
        if status_callback:
            await status_callback("🔍 Searching Trace.moe...")
        result = await EnhancedAIIdentifier._trace_moe_enhanced(img_bytes)
        if result['confidence'] > 0:
            results.append(result)
        
        # Method 2: SauceNAO
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
        """Merge multiple identification results"""
        if not results:
            return {"name": "Unknown Character", "anime": "Unknown Series", "confidence": 0.0}
        
        results.sort(key=lambda x: x['confidence'], reverse=True)
        
        if results[0]['confidence'] >= 0.75:
            return results[0]
        
        name_votes = {}
        anime_votes = {}
        
        for r in results:
            name = r['name'].lower().strip()
            anime = r['anime'].lower().strip()
            
            if name != "unknown character":
                name_votes[name] = name_votes.get(name, 0) + r['confidence']
            
            if anime != "unknown series":
                anime_votes[anime] = anime_votes.get(anime, 0) + r['confidence']
        
        best_name = max(name_votes.items(), key=lambda x: x[1])[0] if name_votes else "unknown character"
        best_anime = max(anime_votes.items(), key=lambda x: x[1])[0] if anime_votes else "unknown series"
        
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
        """Enhanced Trace.moe search"""
        try:
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
                    
                    best_results = [r for r in data['result'][:3] if r.get('similarity', 0) >= 0.60]
                    
                    if not best_results:
                        return {"name": "Unknown", "anime": "Unknown", "confidence": 0.0}
                    
                    top = best_results[0]
                    similarity = top.get('similarity', 0)
                    
                    anilist = top.get('anilist', {})
                    title = anilist.get('title', {})
                    anime = (
                        title.get('english') or
                        title.get('romaji') or
                        title.get('native') or
                        'Unknown Series'
                    )
                    
                    filename = top.get('filename', '')
                    char_name = EnhancedAIIdentifier._smart_extract_name(filename, anime)
                    
                    return {
                        "name": char_name,
                        "anime": anime,
                        "confidence": similarity,
                        "source": "trace.moe"
                    }
                    
        except Exception as e:
            print(f"Trace.moe error: {e}")
            return {"name": "Unknown", "anime": "Unknown", "confidence": 0.0}
    
    @staticmethod
    async def _saucenao_enhanced(img_bytes: bytes) -> Dict:
        """Enhanced SauceNAO search"""
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
                        
                        char_name = "Unknown Character"
                        if data.get('characters'):
                            chars = data['characters']
                            if isinstance(chars, list) and chars:
                                char_name = chars[0]
                            elif isinstance(chars, str):
                                char_name = chars
                        
                        if char_name == "Unknown Character" and data.get('title'):
                            char_name = data['title']
                        
                        anime = (
                            data.get('source') or
                            data.get('material') or
                            data.get('eng_name') or
                            data.get('jp_name') or
                            'Unknown Series'
                        )
                        
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
            print(f"SauceNAO error: {e}")
        
        return {"name": "Unknown", "anime": "Unknown", "confidence": 0.0}
    
    @staticmethod
    async def _ascii2d_enhanced(img_bytes: bytes) -> Dict:
        """Enhanced ASCII2D search"""
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
            print(f"ASCII2D error: {e}")
        
        return {"name": "Unknown", "anime": "Unknown", "confidence": 0.0}
    
    @staticmethod
    async def _iqdb_enhanced(img_bytes: bytes) -> Dict:
        """Enhanced IQDB search"""
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
                    
                    patterns = [
                        r'<td[^>]*>([^<]+?)\s+[/｜]\s+([^<]+?)</td>',
                        r'alt=["\']([^"\']+)["\']',
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
                    
        except Exception as e:
            print(f"IQDB error: {e}")
        
        return {"name": "Unknown", "anime": "Unknown", "confidence": 0.0}
    
    @staticmethod
    def _smart_extract_name(filename: str, anime: str = "") -> str:
        """Extract character name from filename"""
        if not filename:
            return "Unknown Character"
        
        name = re.sub(r'\.[^.]+$', '', filename)
        name = re.sub(r'\[.*?\]', '', name)
        name = re.sub(r'\(.*?\)', '', name)
        name = re.sub(r'[_\-\.]', ' ', name)
        name = re.sub(r'\d{3,}', '', name)
        name = re.sub(r'(?i)(episode|ep|e\d+|s\d+)', '', name)
        
        if anime:
            anime_clean = re.sub(r'[^\w\s]', '', anime.lower())
            name_lower = name.lower()
            for word in anime_clean.split():
                if len(word) > 3:
                    name_lower = name_lower.replace(word, '')
            name = name_lower
        
        name = re.sub(r'\s+', ' ', name).strip()
        words = [w.capitalize() for w in name.split() if len(w) > 1]
        result = ' '.join(words[:4])
        
        return result if len(result) > 2 else "Unknown Character"
    
    @staticmethod
    def _clean_name(text: str) -> str:
        """Clean and normalize names"""
        if not text:
            return ""
        
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'[\[\](){}]', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
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
            quality_bar = "█" * int(char_data["quality_score"] * 10) + "░" * (10 - int(char_data["quality_score"] * 10))
            confidence_bar = "█" * int(char_data["ai_confidence"] * 10) + "░" * (10 - int(char_data["ai_confidence"] * 10))
            
            # Add verification badge
            verification_badge = ""
            if char_data.get('verified_sources', 0) >= 2:
                verification_badge = "✅ Verified Authentic\n"
            
            caption = (
                f'╔══════════════════════╗\n'
                f'  <b>🆔 ID:</b> <code>{char_data["id"]}</code>\n'
                f'╚══════════════════════╝\n\n'
                f'{verification_badge}'
                f'<b>👤 Character:</b> {char_data["name"]}\n'
                f'<b>📺 Anime:</b> {char_data["anime"]}\n\n'
                f'<b>{char_data["rarity_emoji"]} Rarity:</b> {char_data["rarity_name"]}\n\n'
                f'<b>⭐ Quality Score:</b> {char_data["quality_score"]:.2f}/1.00\n'
                f'<code>{quality_bar}</code>\n\n'
                f'<b>🤖 AI Confidence:</b> {char_data["ai_confidence"]:.0%}\n'
                f'<code>{confidence_bar}</code>\n'
                f'<b>🔍 Sources:</b> {char_data.get("verified_sources", 0)} databases\n\n'
                f'<b>📊 Authenticity:</b> {char_data.get("authenticity_score", 100):.0f}%\n\n'
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
    """Main handler with comprehensive verification"""
    status_msg = None
    
    try:
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
            '📥 <b>Step 1/7:</b> Downloading image...\n'
            '<i>Getting high-quality version...</i>',
            parse_mode='HTML'
        )
        
        photo = msg.photo[-1]
        file = await photo.get_file()
        file_bytes = bytes(await file.download_as_bytearray())
        file_size = len(file_bytes) / 1024
        
        await asyncio.sleep(0.5)

        # STEP 2: AI Detection
        await status_msg.edit_text(
            '🤖 <b>Step 2/7:</b> AI Generation Detection...\n'
            '<i>Analyzing image authenticity...</i>\n'
            '<i>Checking for synthetic patterns...</i>\n'
            '<i>Detecting AI artifacts...</i>',
            parse_mode='HTML'
        )
        
        ai_detection = await AIImageDetector.detect_ai_generation(file_bytes)
        
        if not ai_detection.is_authentic:
            warning_text = (
                f'⚠️ <b>AI-Generated Image Detected!</b>\n\n'
                f'<b>AI Probability:</b> {ai_detection.ai_probability:.0%}\n'
                f'<b>Confidence:</b> {ai_detection.confidence:.0%}\n'
                f'<b>Method:</b> {ai_detection.detection_method}\n\n'
                f'<b>Warning Flags:</b>\n'
            )
            
            for flag in ai_detection.warning_flags[:5]:
                warning_text += f'• {flag}\n'
            
            warning_text += (
                f'\n<b>❌ Upload Rejected</b>\n'
                f'<i>Only authentic anime screenshots/artwork allowed.</i>\n'
                f'<i>AI-generated characters from Pixai, NovelAI, etc. are not permitted.</i>'
            )
            
            await status_msg.edit_text(warning_text, parse_mode='HTML')
            return
        
        await asyncio.sleep(0.5)

        # STEP 3: Quality Analysis
        await status_msg.edit_text(
            '📊 <b>Step 3/7:</b> Quality Analysis...\n'
            '<i>Analyzing sharpness, contrast, colors...</i>',
            parse_mode='HTML'
        )
        
        quality = AdvancedQualityAnalyzer.analyze(file_bytes)
        await asyncio.sleep(0.5)

        # STEP 4: Character Identification
        async def update_id_status(status_text):
            try:
                await status_msg.edit_text(
                    f'🔍 <b>Step 4/7:</b> Character Identification...\n'
                    f'<i>{status_text}</i>',
                    parse_mode='HTML'
                )
            except:
                pass
        
        await update_id_status("Searching image databases...")
        char_info = await EnhancedAIIdentifier.identify(file_bytes, update_id_status)
        
        # Check if character was found
        if char_info['confidence'] < 0.50:
            await status_msg.edit_text(
                f'❌ <b>Character Not Identified</b>\n\n'
                f'<b>Confidence:</b> {char_info["confidence"]:.0%}\n'
                f'<b>Sources checked:</b> {char_info.get("source", "multiple")}\n\n'
                f'<i>Could not reliably identify this character.</i>\n'
                f'<i>Please ensure the image is from a known anime/manga.</i>',
                parse_mode='HTML'
            )
            return
        
        await asyncio.sleep(0.5)

        # STEP 5: Database Verification
        async def update_verify_status(status_text):
            try:
                await status_msg.edit_text(
                    f'✅ <b>Step 5/7:</b> Database Verification...\n'
                    f'<i>{status_text}</i>',
                    parse_mode='HTML'
                )
            except:
                pass
        
        await update_verify_status("Verifying character in anime databases...")
        verification = await MultiAnimeAPI.verify_character(
            char_info['name'],
            char_info['anime'],
            update_verify_status
        )
        
        # Require at least 1 database match for unknown characters
        if not verification['verified'] and char_info['confidence'] < 0.75:
            await status_msg.edit_text(
                f'❌ <b>Character Not Verified</b>\n\n'
                f'<b>Character:</b> {char_info["name"]}\n'
                f'<b>Anime:</b> {char_info["anime"]}\n'
                f'<b>Image Confidence:</b> {char_info["confidence"]:.0%}\n'
                f'<b>Database Sources:</b> {verification["sources"]}\n\n'
                f'<i>Character could not be verified in anime databases.</i>\n'
                f'<i>This may be a fake/edited character or from an obscure series.</i>',
                parse_mode='HTML'
            )
            return
        
        # Use verified names if available
        if verification['verified']:
            char_info['name'] = verification['character_name']
            char_info['anime'] = verification['anime_name']
        
        await asyncio.sleep(0.5)

        # STEP 6: Upload to Storage
        await status_msg.edit_text(
            '⬆️ <b>Step 6/7:</b> Uploading to storage...\n'
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
                'Could not upload to Catbox storage.',
                parse_mode='HTML'
            )
            return

        # STEP 7: Save & Publish
        await status_msg.edit_text(
            '💾 <b>Step 7/7:</b> Publishing...\n'
            '<i>Saving to database...</i>',
            parse_mode='HTML'
        )
        
        char_id = await SequenceGen.get_next_id()
        rarity = next(
            (r for r in RarityLevel if r.level == quality.rarity_level),
            RarityLevel.RARE
        )
        
        # Calculate authenticity score
        authenticity_score = (
            (1.0 - ai_detection.ai_probability) * 0.5 +
            (char_info['confidence']) * 0.3 +
            (verification['confidence'] if verification['verified'] else 0.5) * 0.2
        ) * 100
        
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
            
            'quality_score': round(quality.overall, 2),
            'metrics': {
                'sharpness': round(quality.sharpness, 2),
                'contrast': round(quality.contrast, 2),
                'brightness': round(quality.brightness, 2),
                'resolution': round(quality.resolution, 2),
                'color_richness': round(quality.color_richness, 2),
                'edge_density': round(quality.edge_density, 2),
            },
            
            'ai_confidence': round(char_info.get('confidence', 0.0), 2),
            'ai_source': char_info.get('source', 'unknown'),
            
            'authenticity_score': round(authenticity_score, 1),
            'ai_probability': round(ai_detection.ai_probability, 2),
            'verified': verification['verified'],
            'verified_sources': verification['sources'],
            'verification_databases': verification.get('all_sources', []),
            
            'file_size_kb': round(file_size, 1),
            'auto_uploaded': True,
            'upload_timestamp': asyncio.get_event_loop().time()
        }

        channel_msg = await Uploader.send_to_channel(char_data, file_bytes, context)
        
        if channel_msg and channel_msg.photo:
            char_data['message_id'] = channel_msg.message_id
            char_data['file_id'] = channel_msg.photo[-1].file_id

        await collection.insert_one(char_data)

        # SUCCESS
        quality_stars = "⭐" * min(5, int(quality.overall * 5))
        auth_emoji = "✅" if authenticity_score > 80 else "⚠️"
        verify_emoji = "✅" if verification['verified'] else "❌"
        
        success_text = (
            f'✅ <b>Upload Complete!</b>\n\n'
            f'╔═══════════════════════╗\n'
            f'  <b>🆔 ID:</b> <code>{char_id}</code>\n'
            f'╚═══════════════════════╝\n\n'
            f'<b>📝 Character:</b>\n'
            f'├ 👤 {char_info["name"]}\n'
            f'├ 📺 {char_info["anime"]}\n'
            f'└ {rarity.emoji} {rarity.display_name[2:]}\n\n'
            f'<b>🔐 Verification:</b>\n'
            f'├ {auth_emoji} Authenticity: {authenticity_score:.0f}%\n'
            f'├ {verify_emoji} Database Match: {verification["sources"]} sources\n'
            f'├ 🤖 ID Confidence: {char_info["confidence"]:.0%}\n'
            f'└ 🛡️ AI Check: {(1-ai_detection.ai_probability):.0%} authentic\n\n'
            f'<b>📊 Quality:</b> {quality.overall:.2f}/1.00 {quality_stars}\n\n'
            f'<i>Character verified and added to collection!</i>'
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