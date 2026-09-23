SELECT
    i.platform,
    i.channel,
    i.title,
    c.topic,
    c.tone,
    c.confidence
FROM item_labels_comparison c
JOIN items i
    ON i.item_id = c.item_id
WHERE c.model_version = 'llama3.1-8b-v1'
ORDER BY c.confidence DESC;


SELECT
    i.platform,
    i.channel,
    i.title,
    c.topic,
    c.tone,
    c.confidence
FROM item_labels_comparison c
JOIN items i
    ON i.item_id = c.item_id
WHERE c.model_version = 'llama3.1-8b-v1'
  AND c.confidence <= 0.5
ORDER BY c.confidence ASC;



-- 1. Topic distribution by platform
SELECT
    i.platform,
    c.topic,
    COUNT(*) AS count
FROM item_labels_comparison c
JOIN items i ON i.item_id = c.item_id
WHERE c.model_version = 'llama3.1-8b-v1'
GROUP BY i.platform, c.topic
ORDER BY i.platform, count DESC;


-- 2. Tone distribution by platform
SELECT
    i.platform,
    c.tone,
    COUNT(*) AS count
FROM item_labels_comparison c
JOIN items i ON i.item_id = c.item_id
WHERE c.model_version = 'llama3.1-8b-v1'
GROUP BY i.platform, c.tone
ORDER BY i.platform, count DESC;


-- 3. Average confidence for each topic
SELECT
    topic,
    COUNT(*) AS items,
    ROUND(AVG(confidence)::numeric, 2) AS avg_confidence
FROM item_labels_comparison
WHERE model_version = 'llama3.1-8b-v1'
GROUP BY topic
ORDER BY avg_confidence DESC;


-- 4. How many results at each confidence value
SELECT
    confidence,
    COUNT(*) AS count
FROM item_labels_comparison
WHERE model_version = 'llama3.1-8b-v1'
GROUP BY confidence
ORDER BY confidence DESC;


-- 5. Topic + tone combinations
SELECT
    topic,
    tone,
    COUNT(*) AS count
FROM item_labels_comparison
WHERE model_version = 'llama3.1-8b-v1'
GROUP BY topic, tone
ORDER BY count DESC;


-- 6. Everything classified as "other"
SELECT
    i.platform,
    i.channel,
    i.title,
    c.tone,
    c.confidence
FROM item_labels_comparison c
JOIN items i ON i.item_id = c.item_id
WHERE c.model_version = 'llama3.1-8b-v1'
  AND c.topic = 'other'
ORDER BY c.confidence DESC;


-- 7. How many items came from each platform
SELECT
    i.platform,
    COUNT(*) AS count
FROM item_labels_comparison c
JOIN items i ON i.item_id = c.item_id
WHERE c.model_version = 'llama3.1-8b-v1'
GROUP BY i.platform
ORDER BY count DESC;


-- QUERY A: confidence distribution
SELECT
    confidence,
    COUNT(*) AS count,
    ROUND(
        100.0 * COUNT(*) /
        SUM(COUNT(*)) OVER (),
        1
    ) AS percent
FROM item_labels_comparison
WHERE model_version = 'llama3.1-8b-v1'
GROUP BY confidence
ORDER BY confidence DESC;



-- QUERY B: show every "other" classification
SELECT
    i.platform,
    i.channel,
    i.title,
    c.tone,
    c.confidence
FROM item_labels_comparison c
JOIN items i
    ON i.item_id = c.item_id
WHERE c.model_version = 'llama3.1-8b-v1'
  AND c.topic = 'other'
ORDER BY c.confidence DESC;


-- 1. How many TOPIC classifications changed?
SELECT
    COUNT(*) AS topic_changes
FROM item_labels_comparison v1
JOIN item_labels_comparison v2
    ON v1.item_id = v2.item_id
WHERE v1.model_version = 'llama3.1-8b-v1'
  AND v2.model_version = 'llama3.1-8b-v2'
  AND v1.topic <> v2.topic;

  -- 2. How many TONE classifications changed?
SELECT
    COUNT(*) AS tone_changes
FROM item_labels_comparison v1
JOIN item_labels_comparison v2
    ON v1.item_id = v2.item_id
WHERE v1.model_version = 'llama3.1-8b-v1'
  AND v2.model_version = 'llama3.1-8b-v2'
  AND v1.tone <> v2.tone;

  -- 3. V2 topic distribution
SELECT
    topic,
    COUNT(*) AS count,
    ROUND(
        COUNT(*) * 100.0 /
        SUM(COUNT(*)) OVER (),
        1
    ) AS percent
FROM item_labels_comparison
WHERE model_version = 'llama3.1-8b-v2'
GROUP BY topic
ORDER BY count DESC;

-- 4. Show EXACTLY how topics changed from V1 -> V2
SELECT
    v1.topic AS v1_topic,
    v2.topic AS v2_topic,
    COUNT(*) AS count
FROM item_labels_comparison v1
JOIN item_labels_comparison v2
    ON v1.item_id = v2.item_id
WHERE v1.model_version = 'llama3.1-8b-v1'
  AND v2.model_version = 'llama3.1-8b-v2'
  AND v1.topic <> v2.topic
GROUP BY v1.topic, v2.topic
ORDER BY count DESC;


-- 5. Show the actual items whose TOPIC changed
SELECT
    i.platform,
    i.channel,
    i.title,
    v1.topic AS v1_topic,
    v2.topic AS v2_topic
FROM items i
JOIN item_labels_comparison v1
    ON i.item_id = v1.item_id
JOIN item_labels_comparison v2
    ON i.item_id = v2.item_id
WHERE v1.model_version = 'llama3.1-8b-v1'
  AND v2.model_version = 'llama3.1-8b-v2'
  AND v1.topic <> v2.topic
ORDER BY v1.topic, v2.topic;


-- 6. What's STILL classified as other in V2?
SELECT
    i.platform,
    i.channel,
    i.title,
    c.tone
FROM item_labels_comparison c
JOIN items i
    ON i.item_id = c.item_id
WHERE c.model_version = 'llama3.1-8b-v2'
  AND c.topic = 'other'
ORDER BY i.platform, i.channel;


SELECT
    v1.topic AS v1_topic,
    v2.topic AS v2_topic,
    COUNT(*) AS changed_items
FROM item_labels_comparison v1
JOIN item_labels_comparison v2
    ON v1.item_id = v2.item_id
WHERE v1.model_version = 'llama3.1-8b-v1'
  AND v2.model_version = 'llama3.1-8b-v2'
  AND v1.topic <> v2.topic
GROUP BY v1.topic, v2.topic
ORDER BY changed_items DESC;


SELECT
    i.platform,
    i.channel,
    i.title,
    c.tone
FROM item_labels_comparison c
JOIN items i
    ON i.item_id = c.item_id
WHERE c.model_version = 'llama3.1-8b-v2'
  AND c.topic = 'other';

SELECT
    i.platform,
    i.channel,
    i.title,
    v1.topic AS v1_topic,
    v2.topic AS v2_topic,
    v2.tone
FROM items i
JOIN item_labels_comparison v1
    ON i.item_id = v1.item_id
JOIN item_labels_comparison v2
    ON i.item_id = v2.item_id
WHERE v1.model_version = 'llama3.1-8b-v1'
  AND v2.model_version = 'llama3.1-8b-v2'
  AND v2.topic = 'gaming'
ORDER BY i.platform, i.channel;


CREATE TABLE gold_labels (
    item_id    text PRIMARY KEY REFERENCES items(item_id),
    topic      text NOT NULL,
    tone       text,
    notes      text,
    labeled_at timestamptz DEFAULT now()
);

CREATE TABLE gold_sample AS
WITH ranked AS (
    SELECT item_id, topic,
           ROW_NUMBER() OVER (PARTITION BY topic ORDER BY random()) AS rn
    FROM item_labels_comparison
    WHERE model_version = 'llama3.1-8b-v2'
)
SELECT item_id FROM ranked
WHERE topic = 'gaming'
   OR (topic IN ('crime','health','science','finance','other') AND rn <= 5)
   OR (topic NOT IN ('gaming','crime','health','science','finance','other') AND rn <= 3);