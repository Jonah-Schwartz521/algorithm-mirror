CREATE TABLE IF NOT EXISTS participants (
    study_code       text PRIMARY KEY,
    user_token       text UNIQUE,
    enrolled_at      timestamptz,
    baseline_start   date,
    treatment_start  date,
    washout_start    date,
    end_date         date,
    notes            text
);

CREATE OR REPLACE VIEW impressions_with_phase AS
SELECT p.*,
       pa.study_code,
       CASE
           WHEN pa.study_code IS NULL THEN NULL
           WHEN pa.end_date        IS NOT NULL AND p.entered_at::date >  pa.end_date        THEN 'after'
           WHEN pa.washout_start   IS NOT NULL AND p.entered_at::date >= pa.washout_start   THEN 'washout'
           WHEN pa.treatment_start IS NOT NULL AND p.entered_at::date >= pa.treatment_start THEN 'treatment'
           WHEN pa.baseline_start  IS NOT NULL AND p.entered_at::date >= pa.baseline_start  THEN 'baseline'
           ELSE 'pre-study'
       END AS study_phase
FROM impressions p
LEFT JOIN participants pa ON pa.user_token = p.user_token;
