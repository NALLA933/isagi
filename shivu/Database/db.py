from pymongo import MongoClient
import os


MONGO_URI = os.getenv("mongodb+srv://thorfinn00006_db_user:hmQ6sln4mHOWkGax@thorfinn.tnlzhnw.mongodb.net/?retryWrites=true&w=majority")
DB_NAME = os.getenv("DB_NAME", "GRABBING_YOUR_WAIFU")
COLLECTION_NAME = "users"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

def get_user_data(user_id):
    return collection.find_one({"user_id": user_id})

def save_user_data(user_id, user_data):
    collection.update_one({"user_id": user_id}, {"$set": user_data}, upsert=True)
    print("User data saved successfully.")