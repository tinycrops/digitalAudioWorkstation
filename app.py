from flask import Flask, request, jsonify, render_template, send_from_directory
import os
import uuid # For unique filenames
import sys
import logging

# --- Path Setup ---
# Add the workspace root to sys.path to allow imports from object_oriented_agentic_approach
# This assumes app.py is in the workspace root.
WORKSPACE_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.append(WORKSPACE_ROOT)
# Add the parent of object_oriented_agentic_approach if object_oriented_agentic_approach itself isn't directly importable
# This is often needed if 'resources' is not a package.
# A more robust solution is to make object_oriented_agentic_approach.resources a proper package.
sys.path.append(os.path.join(WORKSPACE_ROOT, "object_oriented_agentic_approach"))


# --- Agent and Tool Imports ---
try:
    from object_oriented_agentic_approach.resources.registry.agents.file_access_agent import FileAccessAgent
    from object_oriented_agentic_approach.resources.registry.agents.python_code_exec_agent import PythonExecAgent
    from object_oriented_agentic_approach.resources.registry.tools.retrieve_output_tool import RetrieveOutputTool
    # FileAccessTool is used by FileAccessAgent internally
    # PythonExecTool is used by PythonCodeExecAgent internally
except ImportError as e:
    logging.error(f"Failed to import agent/tool modules: {e}")
    logging.error("Ensure that app.py is in the correct workspace root directory and that Python can find the 'object_oriented_agentic_approach' modules.")
    # Exit if core components can't be imported, as the app won't function.
    sys.exit(f"ImportError: {e}. Please check PYTHONPATH and file structure.")


app = Flask(__name__)

# --- Configuration ---
UPLOAD_FOLDER = os.path.join(WORKSPACE_ROOT, 'uploads')
PROCESSED_OUTPUTS_FOLDER = os.path.join(WORKSPACE_ROOT, 'processed_outputs')
ALLOWED_EXTENSIONS = {'wav', 'mp3', 'flac', 'ogg', 'webm', 'mp4', 'mov', 'avi', 'mkv'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROCESSED_OUTPUTS_FOLDER'] = PROCESSED_OUTPUTS_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_OUTPUTS_FOLDER, exist_ok=True)

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# Get a logger instance for Flask app specific logs if needed, or use Flask's default.
# For agent logs, they use their own logger instances.

# --- Helper Function ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process_audio', methods=['POST'])
def process_audio_route():
    logging.info("Received /process_audio request.")
    try:
        # Instantiate agents and tools per request for statelessness
        file_ingestion_agent = FileAccessAgent()
        # Ensure PythonCodeExecAgent is the one updated for audio
        audio_processing_agent = PythonExecAgent(model_name='o3-mini', reasoning_effort='high') 
        retrieve_output_tool = RetrieveOutputTool()
        logging.info("Agents and tools instantiated for request.")
    except Exception as e:
        logging.error(f"Error instantiating agents/tools for request: {e}", exc_info=True)
        return jsonify({"error": "Backend agent/tool initialization failed. Check server logs."}), 500

    if 'audioFile' not in request.files:
        logging.warning("No audio file part in request.")
        return jsonify({"error": "No audio file part"}), 400
    
    file = request.files['audioFile']
    prompt_text = request.form.get('promptText', '').strip()

    if not prompt_text:
        logging.warning("Empty prompt text in request.")
        return jsonify({"error": "Prompt text cannot be empty."}), 400

    if file.filename == '':
        logging.warning("No selected audio file in request.")
        return jsonify({"error": "No selected audio file"}), 400

    host_uploaded_audio_path = "" # Initialize to ensure it's defined for cleanup
    if file and allowed_file(file.filename):
        try:
            original_filename = file.filename
            # Sanitize filename slightly (though uuid makes it unique anyway)
            safe_original_filename = "".join(c for c in original_filename if c.isalnum() or c in ('.', '_', '-')).strip()
            if not safe_original_filename: safe_original_filename = "uploaded_audio" # fallback
            
            temp_filename = str(uuid.uuid4()) + "_" + safe_original_filename
            host_uploaded_audio_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)
            file.save(host_uploaded_audio_path)
            logging.info(f"Uploaded audio saved to: {host_uploaded_audio_path}")

            # 1. FileAccessAgent: Prepare audio
            logging.info(f"Tasking FileAccessAgent for: {host_uploaded_audio_path}")
            file_access_task_str = f"Prepare the media file located at host path '{host_uploaded_audio_path}' for processing."
            ingestion_output_str = file_ingestion_agent.task(file_access_task_str)
            logging.info(f"FileAccessAgent output: {ingestion_output_str}")

            if not ingestion_output_str or ingestion_output_str.lower().startswith("error"):
                raise Exception(f"File Ingestion Failed: {ingestion_output_str}")

            # 2. AudioProcessingAgent: Process audio
            # The FileAccessAgent output (metadata & container path) is the context for the AudioProcessingAgent
            audio_processing_agent.add_context(ingestion_output_str)
            logging.info(f"Tasking AudioProcessingAgent with prompt: '{prompt_text}' and context from FileAccessAgent.")
            
            container_output_info_str = audio_processing_agent.task(prompt_text)
            logging.info(f"AudioProcessingAgent raw output: {container_output_info_str}")

            if not container_output_info_str or \
               container_output_info_str.lower().startswith("[error]") or \
               container_output_info_str.lower().startswith("error:"):
                raise Exception(f"Audio Processing Failed: {container_output_info_str}")

            # 3. RetrieveOutputTool: Get processed files
            processed_files_info = []
            candidate_paths = []
            
            # First try to split by newlines in a more robust way
            for line in container_output_info_str.splitlines():
                line = line.strip()
                if line:
                    candidate_paths.append(line)
            
            # Fall back to manual split if that didn't work
            if not candidate_paths:
                candidate_paths = [p.strip() for p in container_output_info_str.split('\\n') if p.strip()]
                if not candidate_paths:
                    candidate_paths = [p.strip() for p in container_output_info_str.split('\n') if p.strip()]
            
            actual_paths_to_retrieve = []
            # Look for file paths in the output
            for cp in candidate_paths:
                # Check for the output directory path
                path_start_index = cp.find("/home/sandboxuser/output_audio/")
                if path_start_index != -1:
                    # Extract only the path part (stop at spaces, quotes or other delimiters)
                    path_part = cp[path_start_index:]
                    # Handle potential quotes or other delimiters
                    for delimiter in [' ', '"', "'", ')', ':', ';', ',']:
                        if delimiter in path_part:
                            path_part = path_part.split(delimiter)[0]
                    
                    # Clean up the path
                    path_part = path_part.rstrip('.,;!?')
                    if path_part.endswith("'") or path_part.endswith('"'):
                        path_part = path_part[:-1]
                    
                    actual_paths_to_retrieve.append(path_part)
                elif cp.startswith("/home/sandboxuser/output_audio/"):
                    # Same cleaning for paths that start at the beginning of the line
                    path_part = cp
                    for delimiter in [' ', '"', "'", ')', ':', ';', ',']:
                        if delimiter in path_part:
                            path_part = path_part.split(delimiter)[0]
                    
                    path_part = path_part.rstrip('.,;!?')
                    if path_part.endswith("'") or path_part.endswith('"'):
                        path_part = path_part[:-1]
                    
                    actual_paths_to_retrieve.append(path_part)
                # Check if the line mentions 'saved to:' or similar
                elif "saved to:" in cp.lower() or "saved at:" in cp.lower() or "output file:" in cp.lower():
                    for substr in cp.split():
                        if substr.startswith("/home/sandboxuser/output_audio/"):
                            path_part = substr.rstrip('.,;!?')
                            if path_part.endswith("'") or path_part.endswith('"'):
                                path_part = path_part[:-1]
                            actual_paths_to_retrieve.append(path_part)
            
            # Filter out any invalid looking paths
            actual_paths_to_retrieve = [p for p in actual_paths_to_retrieve if "/" in p and not p.endswith("/")]
            
            unique_paths_to_retrieve = sorted(list(set(actual_paths_to_retrieve)))
            logging.info(f"Unique container paths to retrieve: {unique_paths_to_retrieve}")

            if not unique_paths_to_retrieve:
                # This might not be an error if the LLM just chatted.
                # The PythonExecAgent prompt asks for file paths (7,8) but LLM might not always comply.
                logging.warning(f"Audio processing agent did not return a clear output file path. Agent raw output: {container_output_info_str}")
                # Return the raw agent output if no files were found.
                return jsonify({"message": "Processing finished, but no specific files were identified for retrieval.", "agent_raw_output": container_output_info_str, "processed_files": []})


            for container_path in unique_paths_to_retrieve:
                logging.info(f"Retrieving from container: {container_path}")
                retrieval_args = {
                    "container_file_path": container_path,
                    "host_target_dir": app.config['PROCESSED_OUTPUTS_FOLDER']
                }
                retrieved_host_path_msg = retrieve_output_tool.run(retrieval_args)
                logging.info(f"Retrieval tool output for {container_path}: {retrieved_host_path_msg}")

                if retrieved_host_path_msg.lower().startswith("error"):
                    logging.error(f"Failed to retrieve {container_path}: {retrieved_host_path_msg}")
                    processed_files_info.append({"container_path": container_path, "error": retrieved_host_path_msg})
                else:
                    actual_host_path = retrieved_host_path_msg.split("File retrieved to: ", 1)[-1].strip()
                    filename = os.path.basename(actual_host_path)
                    file_url = f"/processed/{filename}"
                    file_type = ("audio" if any(filename.lower().endswith(ext) for ext in (['.wav', '.mp3', '.flac', '.ogg'] + list(ALLOWED_EXTENSIONS & {'.webm'})))
                                 else "image" if any(filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif'])
                                 else "video" if any(filename.lower().endswith(ext) for ext in (['.mp4', '.mov', '.avi', '.mkv'] + list(ALLOWED_EXTENSIONS & {'.webm'})))
                                 else "unknown")
                    processed_files_info.append({
                        "url": file_url,
                        "filename": filename,
                        "type": file_type,
                        "original_container_path": container_path
                    })
            
            if not any(info.get('url') for info in processed_files_info) and unique_paths_to_retrieve:
                 # If paths were identified but all retrievals failed
                raise Exception(f"Identified output files but failed to retrieve any: {unique_paths_to_retrieve}")

            logging.info(f"Successfully processed request. Processed files: {processed_files_info}")
            return jsonify({"message": "Processing successful", "processed_files": processed_files_info, "agent_raw_output": container_output_info_str})

        except Exception as e:
            logging.error(f"Error during audio processing pipeline: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
        finally:
            # Clean up originally uploaded temp file
            if host_uploaded_audio_path and os.path.exists(host_uploaded_audio_path):
                try:
                    os.remove(host_uploaded_audio_path)
                    logging.info(f"Cleaned up temporary uploaded file: {host_uploaded_audio_path}")
                except OSError as e_remove:
                    logging.error(f"Error cleaning up temp file {host_uploaded_audio_path}: {e_remove}")
    else:
        logging.warning(f"File type not allowed for filename: {file.filename if file else 'N/A'}")
        return jsonify({"error": "File type not allowed"}), 400

# Route to serve processed files from PROCESSED_OUTPUTS_FOLDER
@app.route('/processed/<path:filename>')
def serve_processed_file(filename):
    logging.debug(f"Serving processed file: {filename} from {app.config['PROCESSED_OUTPUTS_FOLDER']}")
    return send_from_directory(app.config['PROCESSED_OUTPUTS_FOLDER'], filename, as_attachment=False)

if __name__ == '__main__':
    print("--- AI Audio Processor ---")
    print("This Flask application provides a frontend for the AI-powered audio processing.")
    print("Please ensure the Docker sandbox container ('sandbox') is running.")
    print("You can start it by navigating to 'object_oriented_agentic_approach/' and running: ")
    print("  python launch_sandbox_container.py")
    print(f"Uploads will be stored temporarily in: {UPLOAD_FOLDER}")
    print(f"Processed files will be made available from: {PROCESSED_OUTPUTS_FOLDER}")
    print("--------------------------")
    app.run(debug=True, port=5001) 