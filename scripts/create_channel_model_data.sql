CREATE TABLE IF NOT EXISTS channel_model_data (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    channel_id BIGINT NOT NULL,
    channel_name VARCHAR(64),
    model_name VARCHAR(64) NOT NULL,
    created_at BIGINT NOT NULL,
    token_used BIGINT NOT NULL DEFAULT 0,
    count BIGINT NOT NULL DEFAULT 0,
    quota BIGINT NOT NULL DEFAULT 0.00,
    INDEX idx_channel_model_created (channel_id, model_name, created_at),
    INDEX idx_model_created (model_name, created_at),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci; 