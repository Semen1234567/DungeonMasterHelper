"""
campaign.py  --  Campaign profiles, character & battle-map management
=====================================================================
Stores campaign profiles, characters and battle maps in JSON files.

Directory structure:
    campaigns/
        campaigns.json          <- list of campaign profiles
        {campaign_id}/
            characters.json     <- characters for this campaign
            maps.json           <- battle maps for this campaign
            maps/               <- map image files (copied here)
"""

import json
import os
import shutil
import uuid
import logging

logger = logging.getLogger(__name__)

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "campaigns")
CAMPAIGNS_JSON = os.path.join(BASE_DIR, "campaigns.json")


# ======================================================================
# Campaign
# ======================================================================
class Campaign:
    __slots__ = ("id", "name", "description")

    def __init__(self, id: str, name: str, description: str = ""):
        self.id = id
        self.name = name
        self.description = description

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name,
                "description": self.description}

    @classmethod
    def from_dict(cls, d: dict) -> "Campaign":
        return cls(d["id"], d["name"], d.get("description", ""))

    @property
    def dir_path(self) -> str:
        return os.path.join(BASE_DIR, self.id)


# ======================================================================
# Character
# ======================================================================
DEFAULT_STATS = {
    "str": 10, "dex": 10, "con": 10,
    "int": 10, "wis": 10, "cha": 10,
    "ac": 10, "hp": 10, "speed": "30 ft",
    "cr": "0",
}

VALID_CHAR_TYPES = ("enemy", "npc")


class Character:
    __slots__ = ("id", "name", "char_type", "category",
                 "appearance", "backstory", "weaknesses", "notes",
                 "stats", "abilities", "image_path")

    def __init__(self, id: str = "", name: str = "",
                 char_type: str = "enemy", category: str = "",
                 appearance: str = "", backstory: str = "",
                 weaknesses: str = "", notes: str = "",
                 stats: dict | None = None, abilities: str = "",
                 image_path: str = ""):
        self.id = id or str(uuid.uuid4())[:8]
        self.name = name
        self.char_type = char_type if char_type in VALID_CHAR_TYPES else "enemy"
        self.category = category
        self.appearance = appearance
        self.backstory = backstory
        self.weaknesses = weaknesses
        self.notes = notes
        self.stats = stats if stats else dict(DEFAULT_STATS)
        self.abilities = abilities
        self.image_path = image_path

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "char_type": self.char_type,
            "category": self.category,
            "appearance": self.appearance,
            "backstory": self.backstory,
            "weaknesses": self.weaknesses,
            "notes": self.notes,
            "stats": dict(self.stats),
            "abilities": self.abilities,
            "image_path": self.image_path,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Character":
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            char_type=d.get("char_type", "enemy"),
            category=d.get("category", ""),
            appearance=d.get("appearance", ""),
            backstory=d.get("backstory", ""),
            weaknesses=d.get("weaknesses", ""),
            notes=d.get("notes", ""),
            stats=d.get("stats", None),
            abilities=d.get("abilities", ""),
            image_path=d.get("image_path", ""),
        )


# ======================================================================
# MapToken  (a token placed on a battle map)
# ======================================================================
VALID_TOKEN_TYPES = ("player", "npc", "enemy")

TOKEN_COLORS = {
    "player": "#a6e3a1",   # green
    "npc":    "#89b4fa",   # blue
    "enemy":  "#f38ba8",   # red
}

TOKEN_ICONS = {
    "player": "\u2659",    # chess pawn
    "npc":    "\u2655",    # chess queen
    "enemy":  "\u2694",    # crossed swords
}


class MapToken:
    __slots__ = ("id", "name", "token_type", "grid_x", "grid_y",
                 "color", "label")

    def __init__(self, id: str = "", name: str = "",
                 token_type: str = "player",
                 grid_x: int = 0, grid_y: int = 0,
                 color: str = "", label: str = ""):
        self.id = id or str(uuid.uuid4())[:8]
        self.name = name
        self.token_type = token_type if token_type in VALID_TOKEN_TYPES else "player"
        self.grid_x = grid_x
        self.grid_y = grid_y
        self.color = color or TOKEN_COLORS.get(token_type, "#cdd6f4")
        self.label = label or (name[:2].upper() if name else "??")

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name,
            "token_type": self.token_type,
            "grid_x": self.grid_x, "grid_y": self.grid_y,
            "color": self.color, "label": self.label,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MapToken":
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            token_type=d.get("token_type", "player"),
            grid_x=d.get("grid_x", 0),
            grid_y=d.get("grid_y", 0),
            color=d.get("color", ""),
            label=d.get("label", ""),
        )


# ======================================================================
# BattleMap
# ======================================================================
class BattleMap:
    __slots__ = ("id", "name", "image_path", "grid_rows", "grid_cols",
                 "tokens")

    def __init__(self, id: str = "", name: str = "",
                 image_path: str = "",
                 grid_rows: int = 20, grid_cols: int = 20,
                 tokens: list | None = None):
        self.id = id or str(uuid.uuid4())[:8]
        self.name = name
        self.image_path = image_path
        self.grid_rows = grid_rows
        self.grid_cols = grid_cols
        self.tokens = tokens if tokens is not None else []

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "image_path": self.image_path,
            "grid_rows": self.grid_rows,
            "grid_cols": self.grid_cols,
            "tokens": [t.to_dict() for t in self.tokens],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BattleMap":
        tokens = [MapToken.from_dict(t) for t in d.get("tokens", [])]
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            image_path=d.get("image_path", ""),
            grid_rows=d.get("grid_rows", 20),
            grid_cols=d.get("grid_cols", 20),
            tokens=tokens,
        )

    def add_token(self, token: MapToken) -> MapToken:
        self.tokens = [t for t in self.tokens if t.id != token.id]
        self.tokens.append(token)
        return token

    def remove_token(self, token_id: str) -> bool:
        before = len(self.tokens)
        self.tokens = [t for t in self.tokens if t.id != token_id]
        return len(self.tokens) < before

    def get_token_at(self, gx: int, gy: int) -> MapToken | None:
        for t in reversed(self.tokens):
            if t.grid_x == gx and t.grid_y == gy:
                return t
        return None


# ======================================================================
# CampaignManager
# ======================================================================
class CampaignManager:
    """Manages campaign profiles, characters, and battle maps."""

    def __init__(self):
        os.makedirs(BASE_DIR, exist_ok=True)
        self._campaigns: list[Campaign] = []
        self._load_campaigns()

    # ------------------------------------------------------------------
    # Campaign CRUD
    # ------------------------------------------------------------------
    def _load_campaigns(self):
        if not os.path.isfile(CAMPAIGNS_JSON):
            return
        with open(CAMPAIGNS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._campaigns = [Campaign.from_dict(d) for d in data]
        logger.info("Loaded %d campaigns", len(self._campaigns))

    def _save_campaigns(self):
        with open(CAMPAIGNS_JSON, "w", encoding="utf-8") as f:
            json.dump([c.to_dict() for c in self._campaigns], f,
                      ensure_ascii=False, indent=2)

    def all_campaigns(self) -> list[Campaign]:
        return list(self._campaigns)

    def get_campaign(self, campaign_id: str) -> Campaign | None:
        for c in self._campaigns:
            if c.id == campaign_id:
                return c
        return None

    def create_campaign(self, name: str, description: str = "") -> Campaign:
        safe_id = "".join(c if c.isalnum() or c in "_-" else "_"
                          for c in name.lower()).strip("_")
        base = safe_id
        counter = 1
        existing_ids = {c.id for c in self._campaigns}
        while safe_id in existing_ids:
            safe_id = f"{base}_{counter}"
            counter += 1

        campaign = Campaign(id=safe_id, name=name, description=description)
        os.makedirs(campaign.dir_path, exist_ok=True)
        os.makedirs(os.path.join(campaign.dir_path, "maps"), exist_ok=True)
        self._campaigns.append(campaign)
        self._save_campaigns()
        logger.info("Created campaign '%s' (id=%s)", name, safe_id)
        return campaign

    def delete_campaign(self, campaign_id: str) -> bool:
        before = len(self._campaigns)
        self._campaigns = [c for c in self._campaigns if c.id != campaign_id]
        if len(self._campaigns) < before:
            self._save_campaigns()
            return True
        return False

    def update_campaign(self, campaign_id: str, name: str = None,
                        description: str = None) -> bool:
        for c in self._campaigns:
            if c.id == campaign_id:
                if name is not None:
                    c.name = name
                if description is not None:
                    c.description = description
                self._save_campaigns()
                return True
        return False

    # ------------------------------------------------------------------
    # Character CRUD  (per campaign)
    # ------------------------------------------------------------------
    def _chars_path(self, campaign_id: str) -> str:
        camp = self.get_campaign(campaign_id)
        if not camp:
            raise ValueError(f"Campaign '{campaign_id}' not found")
        os.makedirs(camp.dir_path, exist_ok=True)
        return os.path.join(camp.dir_path, "characters.json")

    def load_characters(self, campaign_id: str) -> list[Character]:
        path = self._chars_path(campaign_id)
        if not os.path.isfile(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [Character.from_dict(d) for d in data]

    def save_characters(self, campaign_id: str,
                        characters: list[Character]) -> None:
        path = self._chars_path(campaign_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump([c.to_dict() for c in characters], f,
                      ensure_ascii=False, indent=2)

    def add_character(self, campaign_id: str,
                      character: Character) -> Character:
        chars = self.load_characters(campaign_id)
        chars = [c for c in chars if c.id != character.id]
        chars.append(character)
        self.save_characters(campaign_id, chars)
        logger.info("Added character '%s' to campaign '%s'",
                     character.name, campaign_id)
        return character

    def remove_character(self, campaign_id: str,
                         character_id: str) -> bool:
        chars = self.load_characters(campaign_id)
        before = len(chars)
        chars = [c for c in chars if c.id != character_id]
        if len(chars) < before:
            self.save_characters(campaign_id, chars)
            return True
        return False

    def get_character(self, campaign_id: str,
                      character_id: str) -> Character | None:
        for c in self.load_characters(campaign_id):
            if c.id == character_id:
                return c
        return None

    def character_categories(self, campaign_id: str,
                             char_type: str | None = None) -> list[str]:
        chars = self.load_characters(campaign_id)
        seen = set()
        for c in chars:
            if char_type is None or c.char_type == char_type:
                if c.category:
                    seen.add(c.category)
        return sorted(seen)

    def characters_in_category(self, campaign_id: str, category: str,
                               char_type: str | None = None) -> list[Character]:
        chars = self.load_characters(campaign_id)
        result = []
        for c in chars:
            if c.category == category:
                if char_type is None or c.char_type == char_type:
                    result.append(c)
        return result

    # ------------------------------------------------------------------
    # Battle Map CRUD  (per campaign)
    # ------------------------------------------------------------------
    def _maps_json_path(self, campaign_id: str) -> str:
        camp = self.get_campaign(campaign_id)
        if not camp:
            raise ValueError(f"Campaign '{campaign_id}' not found")
        os.makedirs(camp.dir_path, exist_ok=True)
        return os.path.join(camp.dir_path, "maps.json")

    def _maps_dir(self, campaign_id: str) -> str:
        camp = self.get_campaign(campaign_id)
        if not camp:
            raise ValueError(f"Campaign '{campaign_id}' not found")
        maps_dir = os.path.join(camp.dir_path, "maps")
        os.makedirs(maps_dir, exist_ok=True)
        return maps_dir

    def load_maps(self, campaign_id: str) -> list[BattleMap]:
        path = self._maps_json_path(campaign_id)
        if not os.path.isfile(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [BattleMap.from_dict(d) for d in data]

    def save_maps(self, campaign_id: str, maps: list[BattleMap]) -> None:
        path = self._maps_json_path(campaign_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump([m.to_dict() for m in maps], f,
                      ensure_ascii=False, indent=2)

    def add_map(self, campaign_id: str, name: str,
                image_source_path: str,
                grid_rows: int = 20, grid_cols: int = 20) -> BattleMap:
        """Create a new map, copying the image into the campaign folder."""
        maps_dir = self._maps_dir(campaign_id)
        map_id = str(uuid.uuid4())[:8]
        ext = os.path.splitext(image_source_path)[1] or ".png"
        dest_filename = f"{map_id}{ext}"
        dest_path = os.path.join(maps_dir, dest_filename)
        shutil.copy2(image_source_path, dest_path)

        bmap = BattleMap(id=map_id, name=name, image_path=dest_path,
                         grid_rows=grid_rows, grid_cols=grid_cols)
        maps = self.load_maps(campaign_id)
        maps.append(bmap)
        self.save_maps(campaign_id, maps)
        logger.info("Added map '%s' to campaign '%s'", name, campaign_id)
        return bmap

    def update_map(self, campaign_id: str, battle_map: BattleMap) -> None:
        """Save updated map (tokens, grid, etc.)."""
        maps = self.load_maps(campaign_id)
        maps = [m for m in maps if m.id != battle_map.id]
        maps.append(battle_map)
        self.save_maps(campaign_id, maps)

    def remove_map(self, campaign_id: str, map_id: str) -> bool:
        maps = self.load_maps(campaign_id)
        before = len(maps)
        target = None
        for m in maps:
            if m.id == map_id:
                target = m
                break
        if target:
            # Remove image file
            if target.image_path and os.path.isfile(target.image_path):
                try:
                    os.remove(target.image_path)
                except OSError:
                    pass
            maps = [m for m in maps if m.id != map_id]
            self.save_maps(campaign_id, maps)
            return True
        return False

    def get_map(self, campaign_id: str, map_id: str) -> BattleMap | None:
        for m in self.load_maps(campaign_id):
            if m.id == map_id:
                return m
        return None
