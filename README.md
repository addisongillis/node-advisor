# Node Advisor

Node Advisor is a chat-based Blender add-on for reasoning about material node trees.

It scans the active material before each reply and helps with shader structure, naming, and next actions inside the Shader Editor.

## Features

- Chat interface in the Shader Editor sidebar
- Automatic active-material scan before each response
- Guidance for shader structure and organization
- Rename assistance based on visible node names
- One-step guidance for concrete next actions
- Conversation history saved per material

## Requirements

- Blender 5.0 or newer
- Internet connection
- OpenAI API key

## Installation

1. Download `node_advisor.py`
2. In Blender, go to **Edit → Preferences → Add-ons**
3. Click **Install...**
4. Select `node_advisor.py`
5. Enable **Node Advisor**

On first use, the add-on will attempt to install the required Python package automatically.

## Creating an OpenAI API Key

1. Go to https://platform.openai.com/api-keys
2. Sign in or create an account
3. Click **Create new secret key**
4. Copy the key

Note: Keep your API key private. Do not share it or commit it to GitHub.

## Usage

- Open the Shader Editor
- Open the Node Advisor tab in the sidebar
- Select an object with an active material
- Type a message and click Send

Node Advisor inspects the active material and responds based on the live node tree.

## Notes

- Node groups are not expanded in v1
- Image file existence is not validated in v1
- No rendered preview analysis is performed in v1

## Troubleshooting

Add-on installs but does not respond  
Make sure the selected object has an active material and uses nodes.

OpenAI import errors  
Restart Blender after installation. The dependency may have been installed during the current session.

Authentication errors  
Check that OPENAI_API_KEY is set correctly, then restart Blender.

No response or API errors  
Verify internet connection and API key validity.

## Version

Node Advisor v1.0.0

## License

MIT License
