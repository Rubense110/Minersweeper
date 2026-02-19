package com.minersweeper.javaservice.app.validation;

import java.util.Objects;

public final class BadRequestException extends RuntimeException {
    private static final long serialVersionUID = 1L;

    public BadRequestException(String message) {
        super(Objects.requireNonNull(message, "message"));
    }
}
