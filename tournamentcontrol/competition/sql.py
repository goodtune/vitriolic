vitriolic_stage_group_position = """
CREATE OR REPLACE FUNCTION vitriolic_stage_group_position(input_str TEXT)
RETURNS TEXT AS $$
DECLARE
    stage_num INT := NULL;
    group_num INT := NULL;
    position_num INT;
    result_str TEXT := '';
    ordinal_position TEXT := '';
BEGIN
    BEGIN
        SELECT substring(input_str from 'S(\d+)')::INT INTO stage_num;
    EXCEPTION
        WHEN OTHERS THEN
            stage_num := NULL;
    END;

    BEGIN
        SELECT substring(input_str from 'G(\d+)')::INT INTO group_num;
    EXCEPTION
        WHEN OTHERS THEN
            group_num := NULL;
    END;

    SELECT substring(input_str from 'P(\d+)')::INT INTO position_num;

    ordinal_position := position_num ||
        CASE
            WHEN position_num % 10 = 1 AND position_num != 11 THEN 'st'
            WHEN position_num % 10 = 2 AND position_num != 12 THEN 'nd'
            WHEN position_num % 10 = 3 AND position_num != 13 THEN 'rd'
            ELSE 'th'
        END;

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
"""
