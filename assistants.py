import os
import json
import openai
from time import sleep
from dotenv import load_dotenv
import io

from create_ticket import create_ticket, app

load_dotenv()
openai.api_key = os.getenv('OPENAI_API_KEY')


def execute_function(function_name, arguments, from_user):
    if function_name == 'create_ticket':
        subject = arguments.get("subject")
        type_of_question = arguments.get("type_of_question")
        description = arguments.get("description")
        return create_ticket(app.client, subject, from_user, type_of_question, description)
    else:
        return "Function not recognized"


def process_thread_with_assistant(user_query, thread_id=None, assistant_id="asst_omsfgU3PXnHUyr0zn9cFatp4", model="gpt-4-1106-preview", from_user=None):
    response_texts = []
    response_files = []
    in_memory_files = []

    try:
        if not thread_id:
            thread = openai.Client().beta.threads.create()
            thread_id = thread.id
            print(f"New thread created with ID: {thread_id}")
        else:
            print(f"Using existing thread ID: {thread_id}")

        openai.Client().beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_query
        )

        run = openai.Client().beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
            model=model
        )

        while True:
            run_status = openai.Client().beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run.id
            )

            if run_status.status == "requires_action":
                tool_call = run_status.required_action.submit_tool_outputs.tool_calls[0]
                function_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)

                function_output = execute_function(function_name, arguments, from_user)
                function_output_str = json.dumps(function_output)

                openai.Client().beta.threads.runs.submit_tool_outputs(
                    thread_id=thread_id,
                    run_id=run.id,
                    tool_outputs=[{
                        "tool_call_id": tool_call.id,
                        "output": function_output_str
                    }]
                )

            elif run_status.status in ["completed", "failed", "cancelled"]:
                messages = openai.Client().beta.threads.messages.list(thread_id=thread_id)
                for message in messages.data:
                    if message.role == "assistant":
                        for content in message.content:
                            if content.type == "text":
                                response_texts.append(content.text.value)
                            elif content.type == "image_file":
                                file_id = content.image_file.file_id
                                response_files.append(file_id)

                for file_id in response_files:
                    try:
                        file_response = openai.Client().files.content(file_id)
                        file_content = file_response.content if hasattr(file_response, 'content') else file_response

                        in_memory_file = io.BytesIO(file_content)
                        in_memory_files.append(in_memory_file)
                    except Exception as e:
                        print(f"Failed to retrieve content for file ID: {file_id}. Error: {e}")

                break
            sleep(1)

        return {"thread_id": thread_id, "text": response_texts, "in_memory_files": in_memory_files}

    except Exception as e:
        print(f"An error occurred: {e}")
        return {"thread_id": thread_id, "text": [], "in_memory_files": []}


# Example usage
#user_query = "Show me a sample pie chart"
#assistant_id = "asst_P3bdvDVwLXQ49vK2AVjZNCd6"
#from_user_id = "U052337J8QH"
#response = process_thread_with_assistant(user_query, assistant_id, from_user=from_user_id)
#print("Final response:", response)
