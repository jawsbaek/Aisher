-- Initialize SigNoz test database schema
-- This creates the minimal schema required for Aisher integration tests

-- Create database
CREATE DATABASE IF NOT EXISTS signoz_traces;

-- Use the database
USE signoz_traces;

-- Create signoz_index_v2 table (simplified version for testing)
CREATE TABLE IF NOT EXISTS signoz_index_v2 (
    timestamp DateTime64(9) CODEC(DoubleDelta, LZ4),
    traceID FixedString(32) CODEC(ZSTD(1)),
    spanID String CODEC(ZSTD(1)),
    parentSpanID String CODEC(ZSTD(1)),
    serviceName LowCardinality(String) CODEC(ZSTD(1)),
    name LowCardinality(String) CODEC(ZSTD(1)),
    kind Int8 CODEC(T64, ZSTD(1)),
    durationNano UInt64 CODEC(T64, ZSTD(1)),
    statusCode Int16 CODEC(T64, ZSTD(1)),

    -- Tag maps for attributes
    stringTagMap Map(String, String) CODEC(ZSTD(1)),
    numberTagMap Map(String, Float64) CODEC(ZSTD(1)),
    boolTagMap Map(String, Bool) CODEC(ZSTD(1)),

    -- HTTP/RPC fields
    externalHttpMethod LowCardinality(String) CODEC(ZSTD(1)),
    externalHttpUrl LowCardinality(String) CODEC(ZSTD(1)),
    responseStatusCode String CODEC(ZSTD(1)),
    rpcMethod LowCardinality(String) CODEC(ZSTD(1)),

    -- Database fields
    dbSystem LowCardinality(String) CODEC(ZSTD(1)),
    dbName LowCardinality(String) CODEC(ZSTD(1)),

    -- Index
    INDEX idx_service serviceName TYPE bloom_filter(0.001) GRANULARITY 4,
    INDEX idx_name name TYPE bloom_filter(0.001) GRANULARITY 4,
    INDEX idx_duration durationNano TYPE minmax GRANULARITY 1
) ENGINE = MergeTree()
PARTITION BY toDate(timestamp)
ORDER BY (serviceName, -toUnixTimestamp(timestamp))
TTL toDateTime(timestamp) + INTERVAL 7 DAY
SETTINGS index_granularity = 8192;

-- Insert test error data
INSERT INTO signoz_index_v2 (
    timestamp,
    traceID,
    spanID,
    parentSpanID,
    serviceName,
    name,
    kind,
    durationNano,
    statusCode,
    stringTagMap,
    numberTagMap,
    boolTagMap,
    externalHttpMethod,
    externalHttpUrl,
    responseStatusCode,
    rpcMethod,
    dbSystem,
    dbName
) VALUES
-- Error 1: NullPointerException
(
    now() - INTERVAL 10 MINUTE,
    '0123456789abcdef0123456789abcdef',
    'span001',
    '',
    'api-gateway',
    'GET /api/users/{id}',
    2, -- Server
    1500000000, -- 1.5 seconds
    2, -- Error status
    map(
        'exception.type', 'java.lang.NullPointerException',
        'exception.message', 'User object is null',
        'exception.stacktrace', 'java.lang.NullPointerException: User object is null\n\tat com.example.api.UserController.getUser(UserController.java:45)\n\tat com.example.api.UserController$$FastClassBySpringCGLIB.invoke(<generated>)\n\tat org.springframework.web.method.support.InvocableHandlerMethod.invoke(InvocableHandlerMethod.java:221)',
        'http.target', '/api/users/12345',
        'http.host', 'api.example.com'
    ),
    map('http.status_code', 500),
    map('error', true),
    'GET',
    'http://api.example.com/api/users/12345',
    '500',
    '',
    '',
    ''
),
-- Error 2: Same NullPointerException (to test grouping)
(
    now() - INTERVAL 5 MINUTE,
    '0123456789abcdef0123456789abcde1',
    'span002',
    '',
    'api-gateway',
    'GET /api/users/{id}',
    2,
    1600000000,
    2,
    map(
        'exception.type', 'java.lang.NullPointerException',
        'exception.message', 'User object is null',
        'exception.stacktrace', 'java.lang.NullPointerException: User object is null\n\tat com.example.api.UserController.getUser(UserController.java:45)',
        'http.target', '/api/users/67890',
        'http.host', 'api.example.com'
    ),
    map('http.status_code', 500),
    map('error', true),
    'GET',
    'http://api.example.com/api/users/67890',
    '500',
    '',
    '',
    ''
),
-- Error 3: Database connection timeout
(
    now() - INTERVAL 15 MINUTE,
    '0123456789abcdef0123456789abcde2',
    'span003',
    '',
    'payment-service',
    'db.query',
    3, -- Client
    30000000000, -- 30 seconds
    2,
    map(
        'exception.type', 'com.mysql.cj.jdbc.exceptions.CommunicationsException',
        'exception.message', 'Communications link failure - The last packet sent successfully to the server was 30000 milliseconds ago',
        'exception.stacktrace', 'com.mysql.cj.jdbc.exceptions.CommunicationsException: Communications link failure\n\tat com.mysql.cj.jdbc.ConnectionImpl.createNewIO(ConnectionImpl.java:836)\n\tat com.mysql.cj.jdbc.ConnectionImpl.<init>(ConnectionImpl.java:456)',
        'db.statement', 'SELECT * FROM payments WHERE user_id = ?',
        'db.connection_string', 'mysql://db.internal:3306/payments'
    ),
    map('db.timeout_ms', 30000),
    map('error', true),
    '',
    '',
    '',
    '',
    'mysql',
    'payments'
),
-- Error 4: Redis connection refused
(
    now() - INTERVAL 20 MINUTE,
    '0123456789abcdef0123456789abcde3',
    'span004',
    '',
    'cache-service',
    'redis.get',
    3,
    500000000,
    2,
    map(
        'exception.type', 'redis.exceptions.ConnectionError',
        'exception.message', 'Error 111 connecting to redis:6379. Connection refused.',
        'exception.stacktrace', 'redis.exceptions.ConnectionError: Error 111 connecting to redis:6379. Connection refused.\n  File "/usr/local/lib/python3.10/site-packages/redis/connection.py", line 559, in connect\n    sock = self._connect()',
        'db.system', 'redis',
        'net.peer.name', 'redis',
        'net.peer.port', '6379'
    ),
    map('net.peer.port', 6379),
    map('error', true),
    '',
    '',
    '',
    '',
    'redis',
    ''
),
-- Error 5: HTTP 503 from external API
(
    now() - INTERVAL 8 MINUTE,
    '0123456789abcdef0123456789abcde4',
    'span005',
    '',
    'notification-service',
    'POST /api/send',
    3,
    2000000000,
    2,
    map(
        'exception.type', 'HTTPError',
        'exception.message', '503 Service Unavailable: External notification API is down',
        'exception.stacktrace', 'requests.exceptions.HTTPError: 503 Server Error: Service Unavailable\n  File "/app/notification.py", line 23, in send_notification\n    response.raise_for_status()',
        'http.method', 'POST',
        'http.url', 'https://api.notifications.example/v1/send',
        'http.status_code', '503'
    ),
    map('http.status_code', 503),
    map('error', true),
    'POST',
    'https://api.notifications.example/v1/send',
    '503',
    '',
    '',
    ''
),
-- Non-error span (should not be fetched)
(
    now() - INTERVAL 5 MINUTE,
    '0123456789abcdef0123456789abcde5',
    'span006',
    '',
    'api-gateway',
    'GET /api/health',
    2,
    50000000,
    1, -- OK status
    map('http.target', '/api/health'),
    map('http.status_code', 200),
    map('error', false),
    'GET',
    'http://api.example.com/api/health',
    '200',
    '',
    '',
    ''
);
