// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
use std::sync::{Arc, Mutex};
use tauri_plugin_shell::process::CommandChild;

struct EngineState {
    process: Arc<Mutex<Option<CommandChild>>>,
}

#[tauri::command]
async fn stop_engine(state: tauri::State<'_, EngineState>) -> Result<String, String> {
    let mut process_lock = state.process.lock().unwrap();
    if let Some(child) = process_lock.take() {
        #[cfg(windows)]
        {
            let _ = std::process::Command::new("taskkill")
                .args(["/F", "/T", "/PID", &child.pid().to_string()])
                .output();
            let _ = std::process::Command::new("taskkill")
                .args(["/F", "/IM", "ffmpeg.exe"])
                .output();
        }
        
        let _ = child.kill();
        Ok("Process terminated".to_string())
    } else {
        Err("No process is running".to_string())
    }
}

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[tauri::command]
async fn run_python_engine(
    app: tauri::AppHandle,
    state: tauri::State<'_, EngineState>,
    video_path: String,
    process_type: String,
    options_json: String,
) -> Result<String, String> {
    use tauri_plugin_shell::ShellExt;
    use tauri_plugin_shell::process::CommandEvent;
    use tauri::Emitter; // Required for .emit() in Tauri v2

    let shell = app.shell();
    
    // In development (npm run tauri dev), use the raw Python script and venv.
    // In production (npm run tauri build), use the compiled PyInstaller sidecar.
    #[cfg(debug_assertions)]
    let command = {
        let python_path = if cfg!(windows) {
            "../ai_engine/venv/Scripts/python.exe"
        } else {
            "../ai_engine/venv/bin/python"
        };
        let script_name = format!("../ai_engine/{}.py", process_type);
        shell.command(python_path).args([script_name, video_path, options_json])
    };

    #[cfg(not(debug_assertions))]
    let command = {
        shell.sidecar(&process_type)
            .map_err(|e| e.to_string())?
            .args([video_path, options_json])
    };

    let (mut rx, child) = command.spawn().map_err(|e| e.to_string())?;

    *state.process.lock().unwrap() = Some(child);

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
                *state.process.lock().unwrap() = None;
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
    state: tauri::State<'_, EngineState>,
    html: String,
    output_path: String,
    options_json: String, // { duration, fps, width, height, bgColor }
) -> Result<String, String> {
    use tauri_plugin_shell::ShellExt;
    use tauri_plugin_shell::process::CommandEvent;
    use tauri::Emitter;

    let shell = app.shell();

    // Merge html into the options JSON
    let mut options: serde_json::Value = serde_json::from_str(&options_json)
        .unwrap_or(serde_json::json!({}));
    options["html"] = serde_json::Value::String(html);

    let merged_options = options.to_string();

    #[cfg(debug_assertions)]
    let command = {
        let python_path = if cfg!(windows) {
            "../ai_engine/venv/Scripts/python.exe"
        } else {
            "../ai_engine/venv/bin/python"
        };
        let script_name = "../ai_engine/nexus_engine.py".to_string();
        shell.command(python_path).args([script_name, merged_options.clone(), output_path.clone()])
    };

    #[cfg(not(debug_assertions))]
    let command = {
        shell.sidecar("nexus_engine")
            .map_err(|e| e.to_string())?
            .args([&merged_options, &output_path])
    };

    let (mut rx, child) = command.spawn().map_err(|e| e.to_string())?;

    *state.process.lock().unwrap() = Some(child);

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
                *state.process.lock().unwrap() = None;
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

#[tauri::command]
async fn run_nexus_automator(
    app: tauri::AppHandle,
    state: tauri::State<'_, EngineState>,
    options_json: String,
) -> Result<String, String> {
    use tauri_plugin_shell::ShellExt;
    use tauri_plugin_shell::process::CommandEvent;
    use tauri::Emitter;

    let shell = app.shell();

    #[cfg(debug_assertions)]
    let command = {
        let python_path = if cfg!(windows) {
            "../ai_engine/venv/Scripts/python.exe"
        } else {
            "../ai_engine/venv/bin/python"
        };
        let script_name = "../ai_engine/nexus_automator.py".to_string();
        shell.command(python_path).args([script_name, options_json])
    };

    #[cfg(not(debug_assertions))]
    let command = {
        shell.sidecar("nexus_automator")
            .map_err(|e| e.to_string())?
            .args([options_json])
    };

    let (mut rx, child) = command.spawn().map_err(|e| e.to_string())?;

    *state.process.lock().unwrap() = Some(child);

    let mut full_output = String::new();

    while let Some(event) = rx.recv().await {
        match event {
            CommandEvent::Stdout(line) => {
                let out = String::from_utf8_lossy(&line).to_string();
                full_output.push_str(&out);
                let _ = app.emit("automator-stdout", out);
            }
            CommandEvent::Stderr(line) => {
                let out = String::from_utf8_lossy(&line).to_string();
                full_output.push_str(&out);
                let _ = app.emit("automator-stdout", out);
            }
            CommandEvent::Terminated(payload) => {
                *state.process.lock().unwrap() = None;
                if payload.code == Some(0) {
                    return Ok(full_output);
                } else {
                    return Err(format!("Process exited with code {:?}\n\nLog: {}", payload.code, full_output));
                }
            }
            _ => {}
        }
    }

    Ok(full_output)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(EngineState {
            process: Arc::new(Mutex::new(None)),
        })
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![greet, run_python_engine, run_nexus_engine, run_nexus_automator, stop_engine])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}