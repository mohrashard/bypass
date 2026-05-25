// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[tauri::command]
async fn run_python_engine(
    app: tauri::AppHandle,
    video_path: String,
    process_type: String,
    options_json: String,
) -> Result<String, String> {
    use tauri_plugin_shell::ShellExt;
    use tauri_plugin_shell::process::CommandEvent;
    use tauri::Emitter; // Required for .emit() in Tauri v2

    let shell = app.shell();
    
    // Use absolute-style path relative to the executable for better reliability
    let python_path = "../ai_engine/venv/Scripts/python.exe";
    let script_path = format!("../ai_engine/{}.py", process_type);

    let (mut rx, _child) = shell
        .command(python_path)
        .args([script_path, video_path, options_json])
        .spawn()
        .map_err(|e| e.to_string())?;

    let mut full_output = String::new();

    while let Some(event) = rx.recv().await {
        match event {
            CommandEvent::Stdout(line) => {
                let out = String::from_utf8_lossy(&line).to_string();
                full_output.push_str(&out);
                // Emit to frontend for real-time display
                let _ = app.emit("engine-stdout", out);
            }
            CommandEvent::Stderr(line) => {
                let out = String::from_utf8_lossy(&line).to_string();
                full_output.push_str(&out);
                // Emit to frontend for real-time display
                let _ = app.emit("engine-stdout", out); // Use same event for simplicity or "engine-stderr"
            }
            CommandEvent::Terminated(payload) => {
                if payload.code == Some(0) {
                    return Ok(full_output);
                } else {
                    return Err(format!("Process exited with code {:?}", payload.code));
                }
            }
            _ => {}
        }
    }

    Ok(full_output)
}

#[tauri::command]
async fn run_nexus_engine(
    app: tauri::AppHandle,
    html: String,
    output_path: String,
    options_json: String, // { duration, fps, width, height, bgColor }
) -> Result<String, String> {
    use tauri_plugin_shell::ShellExt;
    use tauri_plugin_shell::process::CommandEvent;
    use tauri::Emitter;

    let shell = app.shell();

    let python_path = "../ai_engine/venv/Scripts/python.exe";
    let script_path = "../ai_engine/nexus_engine.py";

    // Merge html into the options JSON
    let mut options: serde_json::Value = serde_json::from_str(&options_json)
        .unwrap_or(serde_json::json!({}));
    options["html"] = serde_json::Value::String(html);

    let merged_options = options.to_string();

    let (mut rx, _child) = shell
        .command(python_path)
        .args([script_path, &merged_options, &output_path])
        .spawn()
        .map_err(|e| e.to_string())?;

    let mut full_output = String::new();

    while let Some(event) = rx.recv().await {
        match event {
            CommandEvent::Stdout(line) => {
                let out = String::from_utf8_lossy(&line).to_string();
                full_output.push_str(&out);
                let _ = app.emit("nexus-stdout", out);
            }
            CommandEvent::Stderr(line) => {
                let out = String::from_utf8_lossy(&line).to_string();
                full_output.push_str(&out);
                let _ = app.emit("nexus-stdout", out);
            }
            CommandEvent::Terminated(payload) => {
                if payload.code == Some(0) {
                    return Ok(output_path); // Return the final output path
                } else {
                    return Err(format!(
                        "Nexus Engine exited with code {:?}\n{}",
                        payload.code, full_output
                    ));
                }
            }
            _ => {}
        }
    }

    Ok(output_path)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![greet, run_python_engine, run_nexus_engine])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}