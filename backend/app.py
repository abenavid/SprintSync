from flask import Flask, request, jsonify
from flask_cors import CORS
from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
import openai
import spacy
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Allow all origins for all routes
CORS(app)

# Load spaCy model
nlp = spacy.load('en_core_web_sm')

# Set OpenAI API key from environment variable
openai.api_key = os.getenv('OPENAI_API_KEY')

# Azure DevOps credentials
MY_ORG = os.getenv('AZURE_DEVOPS_ORG')
MY_PAT = os.getenv('AZURE_DEVOPS_PAT')
MY_PROJECT = os.getenv('AZURE_DEVOPS_PROJECT')

organization_url = f'https://dev.azure.com/{MY_ORG}'
personal_access_token = MY_PAT
project = MY_PROJECT

credentials = BasicAuthentication('', personal_access_token)
connection = Connection(base_url=organization_url, creds=credentials)
wit_client = connection.clients.get_work_item_tracking_client()

@app.route('/api/analyze', methods=['POST'])
def analyze():
  data = request.json
  description = data.get('description')

  if not description:
    return jsonify({'error': 'Description is required'}), 400

  # Generate epic, user stories, and tasks
  generated_content = generate_text(description)
  epic_title, user_stories, tasks = parse_generated_content(generated_content)

  # Create epic in Azure DevOps
  epic = create_work_item('Epic', epic_title)

  # Create user stories and tasks
  user_story_items = [create_work_item('User Story', story, epic) for story in user_stories]
  task_items = [create_work_item('Task', task, epic) for task in tasks]

  response = {
    'epic': epic.fields['System.Title'],
    'user_stories': [item.fields['System.Title'] for item in user_story_items],
    'tasks': [item.fields['System.Title'] for item in task_items]
  }

  return jsonify(response)

def create_work_item(work_item_type, title, parent=None):
  document = [
    {
      'op': 'add',
      'path': '/fields/System.Title',
      'value': title
    }
  ]
  if parent:
    document.append({
      'op': 'add',
      'path': '/relations/-',
      'value': {
        'rel': 'System.LinkTypes.Hierarchy-Reverse',
        'url': parent.url,
        'attributes': {
          'comment': 'Making a new link for the parent'
        }
      }
    })
  return wit_client.create_work_item(document, project, work_item_type)

def generate_text(description):
  prompt = (
    f"Create an epic, user stories, and tasks based on the following description:\n"
    f"Description: {description}\n\n"
    f"1. Epic: Provide a high-level summary of the major feature or goal. Limit it to 2-5 words, keep it simple and high level.\n"
    f"2. User Stories: List detailed descriptions of the functionality involved in the epic.\n"
    f"3. Tasks: Provide individual steps required to complete each user story.\n\n"
    f"Output the epic, user stories, and tasks in a clear format."
  )
  response = openai.ChatCompletion.create(
    model="gpt-4",  # Use appropriate model name
    messages=[
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": prompt}
    ],
    max_tokens=500
  )
  return response.choices[0].message['content'].strip()

def parse_generated_content(content):
  # Parse the content into epic, user stories, and tasks
  lines = content.split('\n')
  epic_title = lines[0].strip()
  user_stories = [line.strip() for line in lines[1:6] if line.strip()]
  tasks = [line.strip() for line in lines[6:] if line.strip()]
  return epic_title, user_stories, tasks

if __name__ == '__main__':
  app.run(debug=True, port=5050)
