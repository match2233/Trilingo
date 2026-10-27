-- ---------------------------------------------------------------- 肌薄（身体训练）
-- 体重记录保留**精确到秒的时间戳**：同一天早晚、饭前饭后、冬夏衣服差别能有 1kg+，
-- 没有时刻就没法解释波动，也没法按天取平均画趋势。
CREATE TABLE IF NOT EXISTS fit_weight (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    at         TEXT NOT NULL,          -- ISO 'YYYY-MM-DDTHH:MM:SS'（本地时间）
    day        TEXT NOT NULL,          -- 冗余一列，方便按天聚合
    kg         REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fit_weight_day ON fit_weight(day);

-- 长期设置：哑铃重量、每个动作的一组次数……改一次管到下次修改
CREATE TABLE IF NOT EXISTS fit_setting (
    k          TEXT PRIMARY KEY,
    v          TEXT NOT NULL
);

-- 力量训练打卡：点一次动作按钮插一行（同一天同一动作可以有多行 = 多组）
CREATE TABLE IF NOT EXISTS fit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    at         TEXT NOT NULL,
    day        TEXT NOT NULL,
    move       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fit_log_day ON fit_log(day, move);

-- 有氧：跑步 km/min/hr；骑行只有 km/min
CREATE TABLE IF NOT EXISTS fit_cardio (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    at         TEXT NOT NULL,
    day        TEXT NOT NULL,
    kind       TEXT NOT NULL,          -- run / bike
    km         REAL NOT NULL DEFAULT 0,
    minutes    REAL NOT NULL DEFAULT 0,
    hr         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_fit_cardio_day ON fit_cardio(day, kind);
