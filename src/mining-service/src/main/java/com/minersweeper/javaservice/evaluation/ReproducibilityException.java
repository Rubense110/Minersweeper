package com.minersweeper.javaservice.evaluation;

/** Safety/ordering failure: not a different scientific outcome for this candidate. */
public class ReproducibilityException extends RuntimeException {
    public final String code;
    public ReproducibilityException(String code) {
        super(code);
        this.code = code;
    }
}
