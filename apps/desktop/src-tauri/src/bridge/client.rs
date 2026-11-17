//! HTTP/1.1 over the backend's Unix domain socket, with the launch secret attached.

use std::path::PathBuf;
use std::time::Duration;

use bytes::Bytes;
use http_body_util::{BodyExt, Full};
use hyper::body::Incoming;
use hyper::header::{AUTHORIZATION, CONTENT_TYPE, HOST};
use hyper::{Request, Response};
use hyper_util::rt::TokioIo;
use serde::Serialize;
use serde_json::Value;
use tokio::net::UnixStream;

use crate::bridge::routes::Method;
use crate::error::BridgeError;
use crate::secret::LaunchSecret;

const MAX_RESPONSE_BYTES: usize = 8 * 1024 * 1024;
const MAX_EVENT_LINE_BYTES: usize = 1024 * 1024;

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct BackendResponse {
    pub status: u16,
    pub body: Value,
}

#[derive(Debug, Clone)]
pub struct UdsClient {
    socket_path: PathBuf,
    secret: LaunchSecret,
    timeout: Duration,
}

impl UdsClient {
    /// For the native-confirmation token only; never serialized or sent to the webview.
    pub fn secret(&self) -> &LaunchSecret {
        &self.secret
    }

    pub fn new(socket_path: PathBuf, secret: LaunchSecret, timeout: Duration) -> Self {
        Self {
            socket_path,
            secret,
            timeout,
        }
    }

    async fn send(
        &self,
        method: Method,
        path: &str,
        body: Option<Vec<u8>>,
    ) -> Result<Response<Incoming>, BridgeError> {
        let stream = UnixStream::connect(&self.socket_path)
            .await
            .map_err(|e| BridgeError::new("backend_unreachable", e.to_string()))?;
        let (mut sender, conn) = hyper::client::conn::http1::handshake(TokioIo::new(stream))
            .await
            .map_err(|e| BridgeError::new("backend_protocol", e.to_string()))?;
        tokio::spawn(async move {
            // Errors here surface through the request/response future below.
            let _ = conn.await;
        });
        let request = Request::builder()
            .method(method.as_str())
            .uri(path)
            .header(HOST, "jarvis.local")
            .header(AUTHORIZATION, format!("Bearer {}", self.secret.expose()))
            .header(CONTENT_TYPE, "application/json")
            .body(Full::new(Bytes::from(body.unwrap_or_default())))
            .map_err(|e| BridgeError::new("bad_request", e.to_string()))?;
        sender
            .send_request(request)
            .await
            .map_err(|e| BridgeError::new("backend_protocol", e.to_string()))
    }

    /// One request/response exchange with a JSON body, bounded by the client timeout.
    pub async fn request_json(
        &self,
        method: Method,
        path: &str,
        body: Option<&Value>,
    ) -> Result<BackendResponse, BridgeError> {
        let encoded = match body {
            Some(v) => Some(
                serde_json::to_vec(v)
                    .map_err(|e| BridgeError::new("bad_request", e.to_string()))?,
            ),
            None => None,
        };
        let exchange = async {
            let response = self.send(method, path, encoded).await?;
            let status = response.status().as_u16();
            let limited = http_body_util::Limited::new(response.into_body(), MAX_RESPONSE_BYTES);
            let bytes = limited
                .collect()
                .await
                .map_err(|e| BridgeError::new("backend_protocol", e.to_string()))?
                .to_bytes();
            let body = if bytes.is_empty() {
                Value::Null
            } else {
                serde_json::from_slice(&bytes)
                    .map_err(|e| BridgeError::new("backend_malformed", e.to_string()))?
            };
            Ok(BackendResponse { status, body })
        };
        tokio::time::timeout(self.timeout, exchange)
            .await
            .map_err(|_| BridgeError::new("backend_timeout", "backend did not answer in time"))?
    }

    /// Streams NDJSON events from `/v1/events`, calling `on_event` per line, until the
    /// stream ends. Returns an error if the stream could not be opened or broke.
    pub async fn stream_events<F>(&self, mut on_event: F) -> Result<(), BridgeError>
    where
        F: FnMut(Value) -> bool,
    {
        let response =
            tokio::time::timeout(self.timeout, self.send(Method::Get, "/v1/events", None))
                .await
                .map_err(|_| BridgeError::new("backend_timeout", "event stream did not open"))??;
        if !response.status().is_success() {
            return Err(BridgeError::new(
                "backend_refused",
                format!("event stream returned {}", response.status()),
            ));
        }
        let mut body = response.into_body();
        let mut buf: Vec<u8> = Vec::new();
        while let Some(frame) = body.frame().await {
            let frame = frame.map_err(|e| BridgeError::new("backend_protocol", e.to_string()))?;
            let Some(data) = frame.data_ref() else {
                continue;
            };
            buf.extend_from_slice(data);
            while let Some(pos) = buf.iter().position(|&b| b == b'\n') {
                let line: Vec<u8> = buf.drain(..=pos).collect();
                let event: Value = serde_json::from_slice(&line[..line.len() - 1])
                    .map_err(|e| BridgeError::new("backend_malformed", e.to_string()))?;
                if !on_event(event) {
                    return Ok(()); // receiver went away
                }
            }
            if buf.len() > MAX_EVENT_LINE_BYTES {
                return Err(BridgeError::new("backend_malformed", "event line too long"));
            }
        }
        Ok(())
    }
}
