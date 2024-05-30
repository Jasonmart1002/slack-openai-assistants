import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
import threading

# Import the function from assistants.py
from assistants import process_thread_with_assistant

load_dotenv()

# Slack app
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

# Dictionary to store mapping between Slack thread_ts and OpenAI thread IDs
thread_mapping = {}
processed_events = set()  # Set to store processed event IDs


# Listen and handle messages
@app.message("")
def message_handler(message, say, ack):
    ack()  # Acknowledge the event immediately
    event_id = message.get('client_msg_id')  # Unique event ID
    if event_id in processed_events:
        app.logger.info(f"Event {event_id} already processed. Skipping.")
        return
    processed_events.add(event_id)

    user_query = message['text']
    assistant_id = "asst_omsfgU3PXnHUyr0zn9cFatp4"
    from_user = message['user']
    slack_thread_ts = message.get('thread_ts', message['ts'])  # Use thread_ts if it exists, otherwise it's a new message

    app.logger.info(f"Received message: {user_query} from user: {from_user} in thread: {slack_thread_ts}")

    def process_and_respond():
        openai_thread_id = thread_mapping.get(slack_thread_ts)
        response = process_thread_with_assistant(user_query, assistant_id, from_user=from_user,
                                                 thread_ts=slack_thread_ts)
        if response:
            # If it's a new thread, store the new OpenAI thread ID
            if openai_thread_id is None:
                new_thread_id = response.get('thread_id')
                if new_thread_id:
                    thread_mapping[slack_thread_ts] = new_thread_id
                    app.logger.info(f"New OpenAI thread created: {new_thread_id} for Slack thread: {slack_thread_ts}")

            # Remove duplicate text responses
            unique_responses = list(set(response.get("text", [])))

            for text in unique_responses:
                say(text, thread_ts=slack_thread_ts)  # Ensure reply is in the same thread
        else:
            say("Sorry, I couldn't process your request.", thread_ts=slack_thread_ts)  # Ensure reply is in the same thread

    threading.Thread(target=process_and_respond).start()


# Start your app
if __name__ == "__main__":
    print("Starting Slack Bolt app...")
    SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN")).start()
