"""
MongoDB Index Conflict Patcher
This MUST be imported BEFORE any other imports that use MongoDB

Save this as: shivu/mongodb_patch.py
"""

from pymongo import collection as pymongo_collection
from pymongo.errors import OperationFailure
import logging

logger = logging.getLogger(__name__)

# Store the original create_index method
_orig_create_index = pymongo_collection.Collection.create_index

def _safe_create_index(self, keys, **kwargs):
    """
    Wrapper for create_index that catches index conflicts
    """
    try:
        return _orig_create_index(self, keys, **kwargs)
    except OperationFailure as e:
        if e.code == 86:  # IndexKeySpecsConflict
            logger.debug(f"Index already exists on {self.name}, skipping")
            return None
        raise

# Apply the monkey patch
pymongo_collection.Collection.create_index = _safe_create_index

logger.info("✅ MongoDB index conflict patch applied")
