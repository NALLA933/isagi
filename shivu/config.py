class Config(object):
    LOGGER = True

    # Get this value from my.telegram.org/apps
    OWNER_ID = "8420981179"
    sudo_users = ["8297659126", "8420981179", "5147822244", "7843303499", "7435049371", "6863917190", "1201153141", "7410843798"]
    GROUP_ID = "-1003150808065"
    TOKEN = "7891572866:AAEKgMqTNK0vQ_mAw63YFKdL6bD2oEiss14"
    mongo_url = "mongodb+srv://teamdaxx123:teamdaxx123@cluster0.ysbpgcp.mongodb.net/?retryWrites=true&w=majority"
    PHOTO_URL = ["https://files.catbox.moe/8722ku.jpeg", "https://files.catbox.moe/kgcrnb.jpeg"]
    SUPPORT_CHAT = "PICK_X_SUPPORT"
    UPDATE_CHAT = "PICK_X_UPDATE"
    BOT_USERNAME = "waifukunbot"
    CHARA_CHANNEL_ID = "-1002621325936"
    api_id = "21705508"
    api_hash = "1d590f4c3d2029a7ef7df087707d7441"

    
class Production(Config):
    LOGGER = True


class Development(Config):
    LOGGER = True
