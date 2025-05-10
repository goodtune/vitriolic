CREATE OR REPLACE FUNCTION vitriolic_stage_group_position(input_str TEXT)
RETURNS TEXT AS $$
DECLARE
    stage_num       INT  := NULL;
    group_num       INT  := NULL;
    position_num    INT;
    result_str      TEXT := '';
    ordinal_position TEXT := '';
BEGIN
    -- Extract stage number
    BEGIN
        SELECT substring(input_str FROM 'S(\d+)')::INT
        INTO stage_num;
    EXCEPTION
        WHEN OTHERS THEN
            stage_num := NULL;
    END;

    -- Extract group number
    BEGIN
        SELECT substring(input_str FROM 'G(\d+)')::INT
        INTO group_num;
    EXCEPTION
        WHEN OTHERS THEN
            group_num := NULL;
    END;

    -- Extract position number
    SELECT substring(input_str FROM 'P(\d+)')::INT
    INTO position_num;

    -- Determine ordinal suffix
    ordinal_position := position_num ||
        CASE
            WHEN position_num % 10 = 1 AND position_num != 11 THEN 'st'
            WHEN position_num % 10 = 2 AND position_num != 12 THEN 'nd'
            WHEN position_num % 10 = 3 AND position_num != 13 THEN 'rd'
            ELSE 'th'
        END;

    -- Build result string
    IF stage_num IS NULL AND group_num IS NULL THEN
        result_str := ordinal_position;
    ELSE
        result_str := ordinal_position || ' ';
    END IF;

    IF stage_num IS NOT NULL THEN
        result_str := result_str || 'Stage ' || stage_num || ' ';
    END IF;

    IF group_num IS NOT NULL THEN
        result_str := result_str || 'Group ' || group_num || ' ';
    END IF;

    RETURN trim(result_str);
END;
$$ LANGUAGE plpgsql;
