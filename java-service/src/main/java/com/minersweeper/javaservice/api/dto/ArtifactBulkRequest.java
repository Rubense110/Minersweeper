package com.minersweeper.javaservice.api.dto;

import java.util.List;

public class ArtifactBulkRequest {
    public String experiment_id;
    public List<String> evaluation_ids;
    public Boolean include_pnml;
}
