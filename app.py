import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
import threading

# Import the function from assistants.py
from assistants import process_thread_with_assistant

load_dotenv()

app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

# Dictionary to store the mapping of Slack thread_ts to OpenAI thread IDs
thread_mapping = {}


# Listen and handle messages
@app.message("")
def message_handler(message, say, ack):
    ack()  # Acknowledge the event immediately
    user_query = message['text']
    assistant_id = "asst_omsfgU3PXnHUyr0zn9cFatp4"
    from_user = message['user']
    thread_ts = message.get('thread_ts', message['ts'])  # Use the thread timestamp if it exists

    def process_and_respond():
        response = process_thread_with_assistant(user_query, slack_thread_ts=thread_ts, assistant_id=assistant_id, from_user=from_user)
        if response:
            # Check if there are any in-memory files to upload
            if response.get("in_memory_files"):
                for i, in_memory_file in enumerate(response["in_memory_files"]):
                    # Use the corresponding text as the annotation for the file
                    annotation_text = response["text"][i] if i < len(response["text"]) else "Here's the file you requested:"
                    app.client.files_upload(
                        channels=message['channel'],
                        file=in_memory_file,
                        filename="image.png",  # or dynamically set the filename
                        initial_comment=annotation_text,  # Text response as annotation
                        title="Uploaded Image",
                        thread_ts=thread_ts  # Ensure the file is posted in the correct thread
                    )
            else:
                # If no files to upload, send text responses normally
                for text in response.get("text", []):
                    say(text, thread_ts=thread_ts)  # Ensure the response is posted in the correct thread
        else:
            say("Sorry, I couldn't process your request.", thread_ts=thread_ts)

    threading.Thread(target=process_and_respond).start()


# Start your app
if __name__ == "__main__":
    SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN")).start()
