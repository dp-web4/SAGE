use futures_util::StreamExt;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use tokio::sync::mpsc;

#[derive(Debug, Clone)]
pub struct OllamaClient {
    base_url: String,
    model: String,
    client: Client,
    /// The context window every request asks for (SAGE_NUM_CTX), or None for Ollama's default.
    ///
    /// WHY (Sprout 2026-10-13): the daemon and the being's heartbeat share one model. The heartbeat
    /// sends num_ctx 16384; the daemon sent none, and Ollama reloads a loaded model whenever a request
    /// asks for a different context, so every noticing would have reloaded the being's 4B (10-30 s)
    /// and the next beat reloaded it back. Same window, one load.
    num_ctx: Option<u32>,
}

#[derive(Serialize)]
struct GenerateRequest<'a> {
    model: &'a str,
    prompt: &'a str,
    stream: bool,
    // Thinking models (qwen3.5, ...) otherwise default to a <think> trace that consumes the token
    // budget and returns an empty visible answer (the request hung to the 120s timeout, blank text).
    // Cognition wants a direct reply, so thinking is off; num_predict bounds the length.
    think: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    system: Option<&'a str>,
    options: GenOpts,
}

#[derive(Serialize)]
struct GenOpts {
    num_predict: i32,
    #[serde(skip_serializing_if = "Option::is_none")]
    num_ctx: Option<u32>,
}

#[derive(Serialize)]
struct CtxOpts {
    num_ctx: u32,
}

#[derive(Serialize)]
struct ChatRequest<'a> {
    model: &'a str,
    messages: &'a [ChatMessage],
    stream: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    options: Option<CtxOpts>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatMessage {
    pub role: String,
    pub content: String,
}

#[derive(Deserialize)]
struct GenerateResponse {
    response: String,
    #[serde(default)]
    done: bool,
}

#[derive(Deserialize)]
struct ChatResponse {
    message: Option<ChatMessageFragment>,
    #[serde(default)]
    done: bool,
}

#[derive(Deserialize)]
struct ChatMessageFragment {
    content: String,
}

#[derive(Deserialize)]
struct ModelListResponse {
    models: Vec<ModelInfo>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct ModelInfo {
    pub name: String,
    #[serde(default)]
    pub size: u64,
}

impl OllamaClient {
    pub fn new(base_url: &str, model: &str) -> Self {
        Self {
            base_url: base_url.trim_end_matches('/').to_string(),
            model: model.to_string(),
            client: Client::builder()
                .timeout(std::time::Duration::from_secs(120))
                .build()
                .unwrap(),
            num_ctx: num_ctx_from(std::env::var("SAGE_NUM_CTX").ok().as_deref()),
        }
    }

    /// The same client asking for a specific context window (tests; callers normally use SAGE_NUM_CTX).
    pub fn with_num_ctx(mut self, num_ctx: Option<u32>) -> Self {
        self.num_ctx = num_ctx;
        self
    }

    pub fn num_ctx(&self) -> Option<u32> {
        self.num_ctx
    }

    pub fn default_local(model: &str) -> Self {
        Self::new("http://localhost:11434", model)
    }

    pub fn model(&self) -> &str {
        &self.model
    }

    /// Non-streaming generate. Returns the full response text.
    pub async fn generate(&self, prompt: &str, system: Option<&str>) -> Result<String, String> {
        let req = GenerateRequest {
            model: &self.model,
            prompt,
            stream: false,
            think: false,
            system,
            options: GenOpts { num_predict: 300, num_ctx: self.num_ctx },
        };

        let resp = self.client
            .post(format!("{}/api/generate", self.base_url))
            .json(&req)
            .send()
            .await
            .map_err(|e| format!("ollama request failed: {e}"))?;

        if !resp.status().is_success() {
            return Err(format!("ollama returned {}", resp.status()));
        }

        let body: GenerateResponse = resp.json().await
            .map_err(|e| format!("ollama response parse error: {e}"))?;

        Ok(body.response)
    }

    /// Non-streaming chat with message history.
    pub async fn chat(&self, messages: &[ChatMessage]) -> Result<String, String> {
        let req = ChatRequest {
            model: &self.model,
            messages,
            stream: false,
            options: self.num_ctx.map(|n| CtxOpts { num_ctx: n }),
        };

        let resp = self.client
            .post(format!("{}/api/chat", self.base_url))
            .json(&req)
            .send()
            .await
            .map_err(|e| format!("ollama chat failed: {e}"))?;

        if !resp.status().is_success() {
            return Err(format!("ollama returned {}", resp.status()));
        }

        let body: ChatResponse = resp.json().await
            .map_err(|e| format!("ollama chat parse error: {e}"))?;

        Ok(body.message.map(|m| m.content).unwrap_or_default())
    }

    /// Streaming generate — sends tokens to the channel as they arrive.
    pub async fn generate_stream(
        &self,
        prompt: &str,
        system: Option<&str>,
        tx: mpsc::Sender<String>,
    ) -> Result<(), String> {
        let req = GenerateRequest {
            model: &self.model,
            prompt,
            stream: true,
            think: false,
            system,
            options: GenOpts { num_predict: 512, num_ctx: self.num_ctx },
        };

        let resp = self.client
            .post(format!("{}/api/generate", self.base_url))
            .json(&req)
            .send()
            .await
            .map_err(|e| format!("ollama stream request failed: {e}"))?;

        if !resp.status().is_success() {
            return Err(format!("ollama returned {}", resp.status()));
        }

        let mut stream = resp.bytes_stream();
        while let Some(chunk) = stream.next().await {
            let bytes = chunk.map_err(|e| format!("stream read error: {e}"))?;
            // Each line is a JSON object
            for line in bytes.split(|&b| b == b'\n') {
                if line.is_empty() {
                    continue;
                }
                if let Ok(parsed) = serde_json::from_slice::<GenerateResponse>(line) {
                    if !parsed.response.is_empty() {
                        let _ = tx.send(parsed.response).await;
                    }
                    if parsed.done {
                        return Ok(());
                    }
                }
            }
        }

        Ok(())
    }

    /// Streaming chat — sends tokens to the channel as they arrive.
    pub async fn chat_stream(
        &self,
        messages: &[ChatMessage],
        tx: mpsc::Sender<String>,
    ) -> Result<(), String> {
        let req = ChatRequest {
            model: &self.model,
            messages,
            stream: true,
            options: self.num_ctx.map(|n| CtxOpts { num_ctx: n }),
        };

        let resp = self.client
            .post(format!("{}/api/chat", self.base_url))
            .json(&req)
            .send()
            .await
            .map_err(|e| format!("ollama chat stream failed: {e}"))?;

        if !resp.status().is_success() {
            return Err(format!("ollama returned {}", resp.status()));
        }

        let mut stream = resp.bytes_stream();
        while let Some(chunk) = stream.next().await {
            let bytes = chunk.map_err(|e| format!("stream read error: {e}"))?;
            for line in bytes.split(|&b| b == b'\n') {
                if line.is_empty() {
                    continue;
                }
                if let Ok(parsed) = serde_json::from_slice::<ChatResponse>(line) {
                    if let Some(msg) = parsed.message {
                        if !msg.content.is_empty() {
                            let _ = tx.send(msg.content).await;
                        }
                    }
                    if parsed.done {
                        return Ok(());
                    }
                }
            }
        }

        Ok(())
    }

    /// List available models.
    pub async fn list_models(&self) -> Result<Vec<ModelInfo>, String> {
        let resp = self.client
            .get(format!("{}/api/tags", self.base_url))
            .send()
            .await
            .map_err(|e| format!("ollama list models failed: {e}"))?;

        let body: ModelListResponse = resp.json().await
            .map_err(|e| format!("ollama model list parse error: {e}"))?;

        Ok(body.models)
    }

    /// The models Ollama has loaded right now (/api/ps), by name. Err if Ollama cannot be asked.
    pub async fn loaded_models(&self) -> Result<Vec<String>, String> {
        let resp = self.client
            .get(format!("{}/api/ps", self.base_url))
            .send()
            .await
            .map_err(|e| format!("ollama ps failed: {e}"))?;
        let body: ModelListResponse = resp.json().await
            .map_err(|e| format!("ollama ps parse error: {e}"))?;
        Ok(body.models.into_iter().map(|m| m.name).collect())
    }

    /// Check if Ollama is reachable.
    pub async fn is_available(&self) -> bool {
        self.client
            .get(format!("{}/api/tags", self.base_url))
            .send()
            .await
            .is_ok()
    }
}


/// SAGE_NUM_CTX as a context window: a positive integer, else None (Ollama's default). Never panics.
pub fn num_ctx_from(raw: Option<&str>) -> Option<u32> {
    raw.and_then(|v| v.trim().parse::<u32>().ok()).filter(|n| *n > 0)
}

#[cfg(test)]
mod num_ctx_tests {
    use super::*;

    #[test]
    fn sage_num_ctx_parses_or_is_absent() {
        assert_eq!(num_ctx_from(Some("16384")), Some(16384));
        assert_eq!(num_ctx_from(Some(" 8192 ")), Some(8192));
        assert_eq!(num_ctx_from(Some("0")), None);
        assert_eq!(num_ctx_from(Some("lots")), None);
        assert_eq!(num_ctx_from(None), None);
    }

    #[test]
    fn requests_carry_num_ctx_only_when_set() {
        let g = GenOpts { num_predict: 300, num_ctx: Some(16384) };
        assert_eq!(serde_json::to_value(&g).unwrap(), serde_json::json!({"num_predict": 300, "num_ctx": 16384}));
        let g = GenOpts { num_predict: 300, num_ctx: None };
        assert_eq!(serde_json::to_value(&g).unwrap(), serde_json::json!({"num_predict": 300}));
        let msgs: Vec<ChatMessage> = vec![];
        let c = ChatRequest { model: "m", messages: &msgs, stream: false, options: Some(CtxOpts { num_ctx: 16384 }) };
        assert_eq!(serde_json::to_value(&c).unwrap()["options"], serde_json::json!({"num_ctx": 16384}));
        let c = ChatRequest { model: "m", messages: &msgs, stream: false, options: None };
        assert!(serde_json::to_value(&c).unwrap().get("options").is_none());
    }
}
