import os
import json
import openai
from time import sleep
from dotenv import load_dotenv
import io  # Import for in-memory file handling
import threading
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# Import the function from assistants.py
from create_ticket import create_ticket, app

load_dotenv()
openai.api_key = os.getenv('OPENAI_API_KEY')

# Initialize the Slack app
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

# Dictionary to store the mapping of Slack thread_ts to OpenAI thread IDs
thread_mapping = {}


def execute_function(function_name, arguments, from_user):
    if function_name == 'create_ticket':
        subject = arguments.get("subject")
        type_of_question = arguments.get("type_of_question")
        description = arguments.get("description")
        return create_ticket(app.client, subject, from_user, type_of_question, description)
    else:
        return "Function not recognized"


def process_thread_with_assistant(user_query, slack_thread_ts=None, assistant_id="asst_omsfgU3PXnHUyr0zn9cFatp4", model="gpt-4-1106-preview", from_user=None):
    response_texts = []
    response_files = []
    in_memory_files = []

    try:
        # Check if there is an existing OpenAI thread ID for the given Slack thread_ts
        openai_thread_id = thread_mapping.get(slack_thread_ts)

        if not openai_thread_id:
            print("Creating a new thread for the user query...")
            thread = openai.Client().beta.threads.create()
            openai_thread_id = thread.id
            # Store the mapping
            thread_mapping[slack_thread_ts] = openai_thread_id
            print(f"New thread created with ID: {openai_thread_id}")
        else:
            print(f"Using existing thread ID: {openai_thread_id}")

        print("Adding the user query as a message to the thread...")
        openai.Client().beta.threads.messages.create(
            thread_id=openai_thread_id,
            role="user",
            content=user_query
        )
        print("User query added to the thread.")

        print("Creating a run to process the thread with the assistant...")
        run = openai.Client().beta.threads.runs.create(
            thread_id=openai_thread_id,
            assistant_id=assistant_id,
            model=model
        )
        print(f"Run created with ID: {run.id}")

        while True:
            print("Checking the status of the run...")
            run_status = openai.Client().beta.threads.runs.retrieve(
                thread_id=openai_thread_id,
                run_id=run.id
            )
            print(f"Current status of the run: {run_status.status}")

            if run_status.status == "requires_action":
                print("Run requires action. Executing specified function...")
                tool_call = run_status.required_action.submit_tool_outputs.tool_calls[0]
                function_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)

                function_output = execute_function(function_name, arguments, from_user)
                function_output_str = json.dumps(function_output)

                print("Submitting tool outputs...")
                openai.Client().beta.threads.runs.submit_tool_outputs(
                    thread_id=openai_thread_id,
                    run_id=run.id,
                    tool_outputs=[{
                        "tool_call_id": tool_call.id,
                        "output": function_output_str
                    }]
                )
                print("Tool outputs submitted.")

            elif run_status.status in ["completed", "failed", "cancelled"]:
                print("Fetching messages added by the assistant...")
                messages = openai.Client().beta.threads.messages.list(thread_id=openai_thread_id)
                for message in messages.data:
                    if message.role == "assistant":
                        for content in message.content:
                            if content.type == "text":
                                response_texts.append(content.text.value)
                            elif content.type == "image_file":
                                file_id = content.image_file.file_id
                                response_files.append(file_id)

                print("Messages fetched. Retrieving content for each file ID...")
                for file_id in response_files:
                    try:
                        print(f"Retrieving content for file ID: {file_id}")
                        file_response = openai.Client().files.content(file_id)
                        file_content = file_response.content if hasattr(file_response, 'content') else file_response

                        in_memory_file = io.BytesIO(file_content)
                        in_memory_files.append(in_memory_file)
                        print(f"In-memory file object created for file ID: {file_id}")
                    except Exception as e:
                        print(f"Failed to retrieve content for file ID: {file_id}. Error: {e}")

                break
            sleep(1)

        return {"thread_id": openai_thread_id, "text": response_texts, "in_memory_files": in_memory_files}

    except Exception as e:
        print(f"An error occurred: {e}")
        return {"thread_id": None, "text": [], "in_memory_files": []}


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
