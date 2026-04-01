bl_info = {
    "name": "Node Advisor",
    "author": "Addison Gillis",
    "version": (1, 0, 0),
    "blender": (5, 0, 0),
    "location": "Shader Editor > Sidebar",
    "description": "AI assistant for Blender nodes with live material scanning and structural guidance",
    "category": "Material",
    "doc_url": "https://github.com/addisongillis/node-advisor",
}

import bpy
import os
import json
import sys
import textwrap
import re
import uuid

from datetime import datetime

import subprocess
import importlib
import site

def ensure_openai():
    user_site = site.getusersitepackages()

    if user_site not in sys.path:
        sys.path.append(user_site)

    try:
        import openai
        return
    except ImportError:
        subprocess.check_call([
            sys.executable,
            "-m",
            "pip",
            "install",
            "--user",
            "openai",
        ])
        importlib.invalidate_caches()

    if user_site not in sys.path:
        sys.path.append(user_site)

ensure_openai()

from openai import OpenAI


SESSION_ID = uuid.uuid4().hex[:6]
SYSTEM_PROMPT = """You are Node Advisor, a Blender material and node assistant.

Before each reply, you are given the current node tree for the active material.

Your job is to help the user reason about shader structure, naming, and next actions without inventing work or confusing internal Blender identifiers with what the user sees.

TRUTH RULES

The current node tree is the source of truth for structure, links, node existence, and active output.
Use the current scan over earlier conversation whenever they conflict.
Earlier conversation is only for the user’s goals, preferences, and recent intent.
Before recommending a node-specific action, verify that the node still exists and that the change has not already been applied.

USER-VISIBLE NAME RULES

Prefer the user-visible node name shown in the node tree.
If a node has a visible label, treat that label as the primary name for user-facing discussion.
Use internal Blender names only when no visible label exists or when the user explicitly asks for internal identifiers.
Do not present internal names as if they were the visible node names.
Do not assume a numbered internal suffix like .001 or .004 is meaningful to the user unless it is visibly shown in the tree.

DUPLICATE-NAME RULES

When the user asks about duplicate names, reason about duplicate user-visible names, not just internal Blender identifiers.
A node is only a duplicate for rename guidance if more than one currently visible node shares the same user-facing name.
Do not treat an internal numbered suffix as proof that a visible duplicate still exists.
When recommending which duplicate to rename next, verify that the visible duplicate still exists in the current scan.

OPERATING MODES

Node Advisor operates in three modes:

Observation Mode
Explicit Guidance Mode
Planning Mode

Determine mode from the user’s request.

OBSERVATION MODE

Use Observation Mode by default.

In Observation Mode:
Respond only to the user’s request.
Do not suggest changes unless the user explicitly asks for guidance or planning.
Do not proactively warn about disconnected nodes or cleanup opportunities.
Treat temporary node states as intentional unless the user asks what to change.
If the user asks what something does, explain it.
If the user asks an unrelated question, say that it is not represented in the current node tree and redirect briefly.
If the node tree is simple and structurally sound, give a brief confirmation and ask what the user wants to achieve. Do not describe the full node chain.

EXPLICIT GUIDANCE MODE

Use Explicit Guidance Mode when the user asks for a concrete next move, such as:
What should I do next
Next
What should I change
Fix this
How should I proceed
Point out the next one
Suggest a new name

In Explicit Guidance Mode:
Recommend exactly one best next action unless the user explicitly asks for alternatives.
That action must be valid in the current node tree.
If multiple actions are required, recommend only the first.
Do not combine unrelated actions into one recommendation.
If no clearly justified next action exists, revert to Observation Mode and ask for the user’s objective.

EXECUTION PRIORITIES

Prefer structural cleanup before parameter tuning.
Prefer deletion of unused or unreached nodes and branches over partial disconnection when they are not contributing to the active result.
When recommending deletion of a node, do not recommend disconnection first, because deletion already removes its links.
Prefer specific node or parameter changes over general advice.
Suggest concrete numeric values when they are justified by the current structure or user goal.
Do not invent arbitrary numbers just to sound specific.
Avoid vague terms like refine, improve, enhance, tweak, or balance unless immediately followed by a concrete instruction.

CONNECTION RULES

Treat socket occupancy as physically constrained: an input accepts only one connection.
Do not recommend an action that would implicitly replace an existing connection.
If replacement is the best path, recommend the disconnection as the next action.
Prefer chaining, blending, or deletion before replacement when those are valid.

PLANNING MODE

Use Planning Mode when the user asks for a broader strategy, such as:
What is the plan
How should this be structured
What order should I tackle this in
How would you build this
Give me the sequence

In Planning Mode:
Multi-step plans are allowed.
Ordered steps are allowed.
Conditional later steps are allowed.
Keep plans concise and grounded in the current node tree.
Do not assume later steps have already happened.
Clearly distinguish the current state from future proposed changes.
Do not over-engineer the plan.

MODE INTERACTION RULES

If the user switches intent, switch modes accordingly.
Observation Mode does not recommend changes unless asked.
Explicit Guidance Mode gives one actionable next step.
Planning Mode may give a short ordered sequence.
If no clearly justified next action exists, revert to Observation Mode and ask for the user’s objective.

NODE IDENTIFICATION RULES

When identifying a node for the user, prefer connection-based and visual descriptions over absolute coordinates.
Use upstream and downstream connections, relative position, and distinguishing parameters before coordinates.
Avoid ordinal references like first, second, third, or fourth unless the numbering is explicit and visible to the user.
For duplicate-name workflows, disambiguation is required. Do not say only “rename Color Ramp” or “rename Noise Texture.”
Instead, identify the node by how it connects, where it sits relative to nearby nodes, or what distinctive settings it has.
Use coordinates only as a fallback, not as the primary locator.
If the user wants to act on multiple nodes but does not explicitly ask for a plan, sequence, or full list, stay in Explicit Guidance Mode and recommend only the next node to act on.

RENAME GUIDANCE RULES

For rename guidance, always refer to the node by the visible name the user sees in the node tree.
If multiple visible nodes share that name, identify the specific node before suggesting a rename.
When suggesting a new name, match the naming convention already visible in the current node tree.
If the tree already favors labels with spaces, continue that style.
If the tree already favors underscores or another consistent scheme, continue that style.
If no clear naming convention is visible, prefer short descriptive names that are easy to read in Blender.
Do not switch naming style arbitrarily within the same conversation.
When the user is renaming duplicates one by one, always verify the current state before naming the next target.
In rename workflows, requests involving multiple duplicates still default to one next rename unless the user explicitly asks for a complete naming plan or full list.

STYLE RULES

Keep replies short and focused.
Do not narrate the entire graph unless the user asks for a broader explanation.
Do not repeat prior explanations unless something materially changed.
Prefer clear direct language.
When referring to nodes, prioritize the visible name the user sees in the editor.
Avoid unnecessary hedging.
Do not ask the user to confirm trivial observations.
When location matters, identify the node in the way most useful to someone looking at the Blender node editor.

DEFAULT RESPONSE STYLE

Use plain language.
Keep most replies to 2 to 4 sentences unless the user asks for a plan or deeper explanation.
In Observation Mode, explain or clarify without pushing action.
In Explicit Guidance Mode, give one concrete next move.
In Planning Mode, give a concise ordered plan.
If the request is ambiguous or no justified action exists, ask what the user wants to accomplish.

GOAL

Node Advisor is a structural shader assistant.
It should help the user understand the current node tree, choose sound next actions, and rename or reorganize nodes without confusing visible labels, internal Blender identifiers, or speculative future state."""


def sanitize_filename(name):
    name = name.strip().lower()
    name = name.replace(" ", "_")
    name = re.sub(r"[^a-z0-9_\\-]", "", name)
    return name or "material"


def get_export_paths(material_name):
    safe_material = sanitize_filename(material_name)

    if bpy.data.filepath:
        blend_dir = os.path.dirname(bpy.data.filepath)
        export_dir = os.path.join(blend_dir, "_node_advisor")
        material_filename = f"{safe_material}_active_material_report.json"
    else:
        export_dir = os.path.join(
            os.path.expanduser("~"),
            "Documents",
            "NodeAdvisor",
            "unsaved",
        )
        material_filename = f"unsaved_{SESSION_ID}_{safe_material}_active_material_report.json"

    os.makedirs(export_dir, exist_ok=True)

    active_path = os.path.join(export_dir, "active_material_report.json")
    material_path = os.path.join(export_dir, material_filename)

    return active_path, material_path


def to_json_safe(value):
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if hasattr(value, "to_list"):
        try:
            return value.to_list()
        except Exception:
            pass

    if hasattr(value, "__iter__") and not isinstance(value, (str, bytes, dict)):
        try:
            return [to_json_safe(v) for v in value]
        except Exception:
            pass

    try:
        return float(value)
    except Exception:
        pass

    try:
        return str(value)
    except Exception:
        return None

def get_node_display_name(node):
    if node.label and node.label.strip():
        return node.label.strip()
    return node.name

def get_socket_default(socket):
    try:
        return to_json_safe(socket.default_value) if not socket.is_linked else None
    except Exception:
        return None


def serialize_socket(socket):
    return {
        "name": socket.name,
        "type": socket.type,
        "linked": socket.is_linked,
        "default": get_socket_default(socket),
    }


def serialize_color_ramp(node):
    ramp = node.color_ramp
    elements = []

    for e in ramp.elements:
        elements.append({
            "position": to_json_safe(e.position),
            "color": to_json_safe(e.color),
        })

    return {
        "interpolation": ramp.interpolation,
        "elements": elements,
    }


def serialize_image_texture(node):
    image = getattr(node, "image", None)
    if not image:
        return None

    filepath = None
    try:
        filepath = image.filepath
    except Exception:
        filepath = None

    packed = False
    try:
        packed = image.packed_file is not None
    except Exception:
        packed = False

    return {
        "image_name": image.name,
        "filepath": filepath,
        "packed": packed,
    }

def get_node_display_name(node):
    if node.label and node.label.strip():
        return node.label.strip()
    return node.name

def serialize_node(node):
    node_data = {
        "id": node.name,
        "display_name": get_node_display_name(node),
        "type": node.bl_idname,
        "location": to_json_safe(node.location),
        "inputs": [serialize_socket(socket) for socket in node.inputs],
        "outputs": [
            {
                "name": socket.name,
                "type": socket.type,
            }
            for socket in node.outputs
        ],
    }

    if node.bl_idname == "ShaderNodeValToRGB":
        node_data["color_ramp"] = serialize_color_ramp(node)

    if node.bl_idname == "ShaderNodeTexImage":
        image_data = serialize_image_texture(node)
        if image_data:
            node_data["image"] = image_data

    return node_data


def serialize_links(node_tree):
    return [
        {
            "from_node": get_node_display_name(link.from_node),
            "from_socket": link.from_socket.name,
            "to_node": get_node_display_name(link.to_node),
            "to_socket": link.to_socket.name,
        }
        for link in node_tree.links
    ]


def get_active_output_node(node_tree):
    for node in node_tree.nodes:
        if node.bl_idname == "ShaderNodeOutputMaterial" and getattr(node, "is_active_output", False):
            return node

    for node in node_tree.nodes:
        if node.bl_idname == "ShaderNodeOutputMaterial":
            return node

    return None


def get_upstream_node_names(node_tree, start_node):
    visited = set()
    stack = [start_node]

    while stack:
        node = stack.pop()
        if node.name in visited:
            continue

        visited.add(node.name)

        for input_socket in node.inputs:
            if input_socket.is_linked:
                for link in input_socket.links:
                    stack.append(link.from_node)

    return visited


def get_reached_node_names(node_tree):
    output_node = get_active_output_node(node_tree)
    if not output_node:
        return set()

    return get_upstream_node_names(node_tree, output_node)


def get_unreached_node_warnings(node_tree):
    warnings = []
    reached = get_reached_node_names(node_tree)

    for node in node_tree.nodes:
        if node.bl_idname == "NodeReroute":
            continue
        if node.name not in reached:
            warnings.append(f"Node does not contribute to active output: {node.name}")

    return warnings


def get_output_summary(node_tree):
    summary = {
        "active_output_node": None,
        "surface": None,
        "volume": None,
        "displacement": None,
    }

    output_node = get_active_output_node(node_tree)
    if not output_node:
        return summary

    summary["active_output_node"] = get_node_display_name(output_node)

    for socket_name, key in [
        ("Surface", "surface"),
        ("Volume", "volume"),
        ("Displacement", "displacement"),
    ]:
        socket = output_node.inputs.get(socket_name)
        if socket and socket.is_linked:
            link = socket.links[0]
            summary[key] = {
                "connected": True,
                "from_node": get_node_display_name(link.from_node),
                "from_socket": link.from_socket.name,
            }
        else:
            summary[key] = {
                "connected": False,
                "from_node": None,
                "from_socket": None,
            }

    return summary


def get_metadata(material):
    obj = bpy.context.object

    return {
        "timestamp": datetime.now().isoformat(),
        "blender_version": {
            "string": bpy.app.version_string,
            "major": bpy.app.version[0],
            "minor": bpy.app.version[1],
            "patch": bpy.app.version[2],
        },
        "object": obj.name if obj else None,
        "material": material.name,
        "material_slot": obj.active_material_index if obj else None,
    }


def get_summary(node_tree):
    type_counts = {}
    for node in node_tree.nodes:
        type_counts[node.bl_idname] = type_counts.get(node.bl_idname, 0) + 1

    return {
        "node_count": len(node_tree.nodes),
        "link_count": len(node_tree.links),
        "node_type_counts": type_counts,
    }


def get_errors(obj, material, node_tree):
    errors = []

    if not obj:
        errors.append("No active object.")
        return errors

    if not material:
        errors.append("No active material.")
        return errors

    if not material.use_nodes:
        errors.append("Material does not use nodes.")
        return errors

    if not get_active_output_node(node_tree):
        errors.append("No Material Output node found.")

    return errors


def get_duplicate_name_warnings(node_tree):
    warnings = []
    counts = {}

    for node in node_tree.nodes:
        counts[node.name] = counts.get(node.name, 0) + 1

    duplicate_names = [name for name, count in counts.items() if count > 1]
    for name in duplicate_names:
        warnings.append(f"Duplicate node name: {name}")

    return warnings


def get_disconnected_branch_warnings(node_tree):
    warnings = []

    connected_node_names = set()
    for link in node_tree.links:
        connected_node_names.add(link.from_node.name)
        connected_node_names.add(link.to_node.name)

    for node in node_tree.nodes:
        if node.bl_idname == "NodeReroute":
            continue
        if node.name not in connected_node_names:
            warnings.append(f"Node is fully disconnected: {node.name}")

    return warnings


def build_report():
    obj = bpy.context.object
    if not obj:
        return {"error": "No active object"}

    material = obj.active_material
    if not material:
        return {"error": "No active material"}

    if not material.use_nodes:
        return {"error": "Material does not use nodes"}

    node_tree = material.node_tree

    report = {
        "json_dump": {
            "nodes": [serialize_node(node) for node in node_tree.nodes],
            "links": serialize_links(node_tree),
        },
        "metadata": get_metadata(material),
        "summary": get_summary(node_tree),
        "outputs": get_output_summary(node_tree),
        "errors": get_errors(obj, material, node_tree),
        "warnings": [],
        "notes": [
            "v1 limitations: node groups are not expanded.",
            "v1 limitations: image file existence is not validated.",
            "v1 limitations: no rendered preview analysis is performed.",
        ],
    }

    report["warnings"].extend(get_disconnected_branch_warnings(node_tree))
    report["warnings"].extend(get_duplicate_name_warnings(node_tree))
    report["warnings"].extend(get_unreached_node_warnings(node_tree))

    return report


def export_report():
    report = build_report()

    if "error" in report:
        return report

    material_name = report["metadata"]["material"]
    active_path, material_path = get_export_paths(material_name)

    with open(active_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=4, default=to_json_safe)

    with open(material_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=4, default=to_json_safe)

    return {
        "active_path": active_path,
        "material_path": material_path,
        "report_data": report,
    }
    
def get_library_path():
    base_dir = os.path.join(
        os.path.expanduser("~"),
        "Documents",
        "NodeAdvisor",
    )
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, "conversations.json")


def load_conversation_library():
    library_path = get_library_path()

    if not os.path.exists(library_path):
        library = {
            "version": 1,
            "conversations": {},
        }
        with open(library_path, "w", encoding="utf-8") as f:
            json.dump(library, f, indent=4)
        return library

    try:
        with open(library_path, "r", encoding="utf-8") as f:
            library = json.load(f)
    except Exception:
        library = {
            "version": 1,
            "conversations": {},
        }

    if not isinstance(library, dict):
        library = {}

    if "version" not in library:
        library["version"] = 1

    if "conversations" not in library or not isinstance(library["conversations"], dict):
        library["conversations"] = {}

    return library


def save_conversation_library(library):
    library_path = get_library_path()

    with open(library_path, "w", encoding="utf-8") as f:
        json.dump(library, f, indent=4)
        

def get_material_conversation_id(material):
    if material is None:
        return None

    return material.get("node_advisor_conversation_id")

def ensure_material_conversation_id(material):
    if material is None:
        return None

    conversation_id = material.get("node_advisor_conversation_id")
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
        material["node_advisor_conversation_id"] = conversation_id

    return conversation_id

def get_or_create_conversation(material):
    conversation_id = ensure_material_conversation_id(material)

    library = load_conversation_library()

    conversations = library["conversations"]

    if conversation_id not in conversations:
        conversations[conversation_id] = {
            "conversation_id": conversation_id,
            "material_name": material.name if material else "Unknown",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "messages": [],
        }

        save_conversation_library(library)

    return conversations[conversation_id]

def append_message_to_conversation(material, role, content):
    if material is None or not content.strip():
        return

    conversation_id = ensure_material_conversation_id(material)
    library = load_conversation_library()
    conversations = library["conversations"]

    if conversation_id not in conversations:
        conversations[conversation_id] = {
            "conversation_id": conversation_id,
            "material_name": material.name,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "messages": [],
        }

    conversation = conversations[conversation_id]
    conversation["material_name"] = material.name
    conversation["updated_at"] = datetime.utcnow().isoformat()
    conversation["messages"].append({
        "role": role,
        "content": content,
    })

    save_conversation_library(library)


def build_chat_context_for_material(material):
    if material is None:
        return ""

    conversation_id = get_material_conversation_id(material)
    if not conversation_id:
        return ""

    library = load_conversation_library()
    conversation = library["conversations"].get(conversation_id)

    if not conversation:
        return ""

    lines = []

    for msg in conversation.get("messages", []):
        role = msg.get("role", "").upper()
        content = msg.get("content", "").strip()
        if role and content:
            lines.append(f"{role}: {content}")

    return "\n\n".join(lines)

def get_conversation_messages_for_material(material):
    if material is None:
        return []

    conversation_id = get_material_conversation_id(material)
    if not conversation_id:
        return []

    library = load_conversation_library()
    conversation = library["conversations"].get(conversation_id)

    if not conversation:
        return []

    return conversation.get("messages", [])
    
def build_connection_summary(report_data):
    lines = []

    links = report_data.get("json_dump", {}).get("links", [])

    occupied_inputs = {}

    for link in links:
        key = f"{link['to_node']}.{link['to_socket']}"
        occupied_inputs[key] = f"{link['from_node']}.{link['from_socket']}"

    lines.append("Occupied inputs:")
    for target, source in occupied_inputs.items():
        lines.append(f"- {target} ← {source}")

    return "\n".join(lines)

def analyze_active_material(user_message, chat_context):
    report_data = build_report()
    
    connection_summary = build_connection_summary(report_data)

    if "error" in report_data:
        return report_data

    print("Node Advisor: Using in-memory report")
    print("Material:", report_data.get("metadata", {}).get("material"))

    client = OpenAI()

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        "Conversation so far:\n"
        f"{chat_context}\n\n"
        "Latest user message:\n"
        f"{user_message}\n\n"
        "Connection summary:\n"
        f"{connection_summary}\n\n"
        "Current active material report:\n"
        f"{json.dumps(report_data)}"
    )

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )

    analysis_text = response.output_text.strip()

    print("Node Advisor: API call successful")
    print("Node Advisor Analysis:")
    print(analysis_text)

    return {
        "report_data": report_data,
        "analysis_text": analysis_text,
    }

def force_ui_redraw(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()

class NODE_ADVISOR_OT_send_message(bpy.types.Operator):
    bl_idname = "node_advisor.send_message"
    bl_label = "Send"
    
    def execute(self, context):
        print("---- NODE ADVISOR CONTEXT DEBUG ----")

        print("AREA:", context.area.type if context.area else None)
        print("REGION:", context.region.type if context.region else None)

        space = context.space_data
        print("SPACE:", space.type if space else None)

        print("WINDOW:", context.window)

        try:
            print("BUTTON_PROP:", context.button_prop)
        except Exception:
            print("BUTTON_PROP: None")

        try:
            print("ACTIVE_OPERATOR:", context.active_operator)
        except Exception:
            print("ACTIVE_OPERATOR: None")

        print("------------------------------------")

        scene = context.scene
        material = context.object.active_material if context.object else None
        user_text = scene.node_advisor_input.strip()

        if not user_text:
            self.report({'WARNING'}, "No message entered.")
            return {'CANCELLED'}

        if material is None:
            self.report({'ERROR'}, "No active material.")
            return {'CANCELLED'}

        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()

        chat_context = build_chat_context_for_material(material)

        result = analyze_active_material(user_text, chat_context)
        
        append_message_to_conversation(material, "user", user_text)

        if "error" in result:
            self.report({'ERROR'}, result["error"])
            return {'CANCELLED'}

        append_message_to_conversation(material, "assistant", result["analysis_text"])

        scene.node_advisor_input = ""
        return {'FINISHED'}

class NODE_ADVISOR_PT_panel(bpy.types.Panel):
    bl_label = "Node Advisor"
    bl_idname = "NODE_ADVISOR_PT_panel"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Node Advisor"

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space is not None and getattr(space, "tree_type", "") == "ShaderNodeTree"

    def draw_message(self, layout, role, content):
        box = layout.box()
        header = box.row()
        header.label(text=role.capitalize())

        paragraphs = content.split("\n\n")

        for paragraph in paragraphs:
            wrapped_lines = textwrap.wrap(paragraph, width=58) or [""]
            for line in wrapped_lines:
                box.label(text=line)
            box.separator()

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        transcript_box = layout.box()
        transcript_box.label(text="Chat")

        material = context.object.active_material if context.object else None
        conversation_messages = get_conversation_messages_for_material(material)

        if len(conversation_messages) == 0:
            transcript_box.label(text="No messages yet.")
        else:
            for msg in conversation_messages:
                self.draw_message(
                    transcript_box,
                    msg.get("role", ""),
                    msg.get("content", ""),
                )

        layout.separator()
        layout.label(text="Message")

        layout.prop(scene, "node_advisor_input", text="")
        layout.operator("node_advisor.send_message", text="Send")

classes = (
    NODE_ADVISOR_OT_send_message,
    NODE_ADVISOR_PT_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.node_advisor_input = bpy.props.StringProperty(
        name="Node Advisor Input",
        description="Message to Node Advisor",
        default="",
        options={'TEXTEDIT_UPDATE'}
    )

def unregister():

    del bpy.types.Scene.node_advisor_input

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()