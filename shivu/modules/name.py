from pyrogram import Client, filters
from shivu import user_collection, collection
from shivu import shivuu as bot
import asyncio

AUTHORIZED_USER_ID = 5147822244
BATCH_SIZE = 50

@bot.on_message(filters.command(["solve"]))
async def update_names(client, message):
    if message.from_user.id != AUTHORIZED_USER_ID:
        await message.reply("You are not authorized to use this command.")
        return

    status_msg = await message.reply("Starting character name update process...")
    
    stats = {
        'users_processed': 0,
        'users_updated': 0,
        'users_failed': 0,
        'characters_updated': 0,
        'characters_not_found': 0
    }

    try:
        print("Caching master collection...")
        master_collection = {}
        async for char in collection.find():
            master_collection[char['id']] = char
        
        print(f"Cached {len(master_collection)} characters from master collection")
        
        total_users = await user_collection.count_documents({})
        print(f"Total users to process: {total_users}")

        async for user in user_collection.find():
            stats['users_processed'] += 1
            
            if not user.get('characters'):
                print(f"User {user.get('id', 'unknown')} has no characters, skipping...")
                continue

            updated_characters = []
            user_has_changes = False

            for character in user['characters']:
                char_id = character.get('id')
                
                if not char_id:
                    print(f"Character without ID found for user {user.get('id')}")
                    updated_characters.append(character)
                    continue

                original_character = master_collection.get(char_id)
                
                if original_character:
                    original_name = original_character.get('name', character.get('name'))
                    
                    if original_name != character.get('name'):
                        user_has_changes = True
                        stats['characters_updated'] += 1
                    
                    updated_characters.append({
                        'id': char_id,
                        'name': original_name,
                        'anime': character.get('anime', original_character.get('anime', '')),
                        'img_url': character.get('img_url', original_character.get('img_url', '')),
                        'rarity': character.get('rarity', original_character.get('rarity', '')),
                        'count': character.get('count', 1)
                    })
                else:
                    stats['characters_not_found'] += 1
                    print(f"Character ID {char_id} not found in master collection")
                    updated_characters.append(character)

            if user_has_changes:
                try:
                    result = await user_collection.update_one(
                        {'id': user['id']},
                        {'$set': {'characters': updated_characters}}
                    )
                    
                    if result.modified_count == 1:
                        stats['users_updated'] += 1
                        print(f"Updated user: {user['id']}")
                    else:
                        stats['users_failed'] += 1
                        print(f"Failed to update user: {user['id']}")
                        
                except Exception as e:
                    stats['users_failed'] += 1
                    print(f"Error updating user {user.get('id')}: {e}")

            if stats['users_processed'] % BATCH_SIZE == 0:
                progress = (stats['users_processed'] / total_users) * 100
                await status_msg.edit_text(
                    f"Processing... {stats['users_processed']}/{total_users} ({progress:.1f}%)\n"
                    f"Updated: {stats['users_updated']} users\n"
                    f"Characters fixed: {stats['characters_updated']}"
                )
                await asyncio.sleep(0.1)

        final_message = (
            f"Update process completed\n\n"
            f"Users processed: {stats['users_processed']}\n"
            f"Users updated: {stats['users_updated']}\n"
            f"Users failed: {stats['users_failed']}\n"
            f"Characters updated: {stats['characters_updated']}\n"
            f"Characters not found: {stats['characters_not_found']}"
        )
        
        await status_msg.edit_text(final_message)
        print(final_message)
        
    except Exception as e:
        error_msg = f"An error occurred: {str(e)}"
        await status_msg.edit_text(error_msg)
        print(error_msg)
        import traceback
        traceback.print_exc()