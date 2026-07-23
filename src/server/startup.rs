//! Server startup and configuration

use super::handlers::{AppState, ServerConfig};
use actix_web::{web, App, HttpResponse, HttpServer};
use std::sync::Arc;

fn load_rustls_config(cert_path: &str, key_path: &str) -> std::io::Result<rustls::ServerConfig> {
    use std::fs::File;
    use std::io::BufReader;

    let cert_file = File::open(cert_path).map_err(|e| {
        std::io::Error::new(
            std::io::ErrorKind::NotFound,
            format!("Failed to open cert file '{}': {}", cert_path, e),
        )
    })?;
    let mut cert_reader = BufReader::new(cert_file);
    let certs: Vec<_> = rustls_pemfile::certs(&mut cert_reader)
        .collect::<Result<Vec<_>, _>>()
        .map_err(|e| {
            std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("Failed to parse certs from '{}': {}", cert_path, e),
            )
        })?;

    if certs.is_empty() {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            format!("No valid certificates found in '{}'", cert_path),
        ));
    }

    let key_file = File::open(key_path).map_err(|e| {
        std::io::Error::new(
            std::io::ErrorKind::NotFound,
            format!("Failed to open key file '{}': {}", key_path, e),
        )
    })?;
    let mut key_reader = BufReader::new(key_file);
    let key = rustls_pemfile::private_key(&mut key_reader)
        .map_err(|e| {
            std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("Failed to parse private key from '{}': {}", key_path, e),
            )
        })?
        .ok_or_else(|| {
            std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("No private key found in '{}'", key_path),
            )
        })?;

    // Ensure default crypto provider is installed for rustls 0.23
    let _ = rustls::crypto::ring::default_provider().install_default();

    let tls_config = rustls::ServerConfig::builder()
        .with_no_client_auth()
        .with_single_cert(certs, key)
        .map_err(|e| {
            std::io::Error::new(
                std::io::ErrorKind::InvalidInput,
                format!("TLS config error: {}", e),
            )
        })?;

    Ok(tls_config)
}

/// Start the Actix-web server
pub async fn start_server(config: ServerConfig, state: Arc<AppState>) -> std::io::Result<()> {
    let addr = format!("{}:{}", config.host, config.port);

    // Ensure body limit from config is live on the shared state
    state
        .max_body_size
        .store(config.max_body_size, std::sync::atomic::Ordering::Relaxed);

    let pid = std::process::id();
    let route_count = state.routes.load().route_count();

    // Stylish Banner (Fiber-like)
    use colored::Colorize;

    let is_https = config.ssl_cert.is_some() && config.ssl_key.is_some();
    let protocol = if is_https { "https" } else { "http" };

    let version = env!("CARGO_PKG_VERSION");
    let banner_text = format!("BustAPI v{}", version);

    // Prepare all lines
    let line1 = banner_text.clone();
    let line2 = format!("{}://{}", protocol, addr);
    let line3 = format!("(bound on host {} and port {})", config.host, config.port);
    let line4 = String::new(); // Empty line
    let line6 = format!(
        "Debug ............ {}  PID ............. {}",
        config.debug, pid
    );

    // Helper function to center text in box
    let center_in_box = |text: &str, width: usize| {
        let text_len = text.len();
        let total_padding = width.saturating_sub(text_len);
        let pad_left = total_padding / 2;
        let pad_right = total_padding - pad_left;
        format!(
            "│{}{}{}│",
            " ".repeat(pad_left),
            text,
            " ".repeat(pad_right)
        )
    };

    // Print the box
    // Print the box only if requested
    if let Some(processes_count) = config.show_banner {
        // Re-calculate line5 with correct process count
        let line5 = format!(
            "Handlers ............. {}   Processes ........... {}",
            route_count, processes_count
        );

        let max_width = [
            line1.len(),
            line2.len(),
            line3.len(),
            line5.len(),
            line6.len(),
        ]
        .iter()
        .max()
        .unwrap_or(&0)
            + 4;

        let horizontal_line = "─".repeat(max_width);

        println!("┌{}┐", horizontal_line);
        // For line1, calculate padding based on uncolored text, then apply color
        let line1_len = line1.len();
        let total_padding = max_width.saturating_sub(line1_len);
        let pad_left = total_padding / 2;
        let pad_right = total_padding - pad_left;
        println!(
            "│{}{}{}│",
            " ".repeat(pad_left),
            line1.cyan().bold(),
            " ".repeat(pad_right)
        );
        println!("{}", center_in_box(&line2, max_width));
        println!("{}", center_in_box(&line3, max_width));
        println!("{}", center_in_box(&line4, max_width));
        println!("{}", center_in_box(&line5, max_width));
        println!("{}", center_in_box(&line6, max_width));
        println!("└{}┘", horizontal_line);
    }

    let tls_config = match (&config.ssl_cert, &config.ssl_key) {
        (Some(cert), Some(key)) => Some(load_rustls_config(cert, key)?),
        _ => None,
    };

    // Enable SO_REUSEPORT for multi-process scalability
    // This allows multiple processes to bind to the same port on Linux
    let socket = socket2::Socket::new(
        socket2::Domain::IPV4,
        socket2::Type::STREAM,
        Some(socket2::Protocol::TCP),
    )?;

    #[cfg(unix)]
    {
        if let Err(e) = socket.set_reuse_port(true) {
            tracing::warn!("⚠️ Failed to set SO_REUSEPORT: {}", e);
        }
    }
    socket.set_reuse_address(true)?;

    let addr: std::net::SocketAddr = format!("{}:{}", config.host, config.port)
        .parse()
        .map_err(|e| std::io::Error::new(std::io::ErrorKind::InvalidInput, e))?;

    socket.bind(&addr.into())?;
    socket.listen(1024)?; // Backlog 1024

    let listener: std::net::TcpListener = socket.into();

    async fn health_check(_state: web::Data<AppState>) -> HttpResponse {
        tracing::debug!("health_check called with state");
        HttpResponse::Ok().body("OK")
    }

    let server = HttpServer::new(move || {
        tracing::debug!("App factory running");

        App::new()
            .app_data(web::Data::from(state.clone()))
            .route("/health", web::get().to(health_check))
            .route("/{tail:.*}", web::to(super::handlers::handle_request))
            .default_service(web::to(super::handlers::handle_request))
    })
    .workers(config.workers);

    if let Some(tls_config) = tls_config {
        server.listen_rustls_0_23(listener, tls_config)?.run().await
    } else {
        server.listen(listener)?.run().await
    }
}
