package com.kawai.mochi;

import org.junit.Test;

import java.lang.reflect.Method;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

public class StickerPackValidatorTest {

    @Test
    public void testCheckStringValidityValidString() throws Exception {
        Method method = StickerPackValidator.class.getDeclaredMethod("checkStringValidity", String.class);
        method.setAccessible(true);

        method.invoke(null, "valid_identifier-123");
        method.invoke(null, "valid.identifier, 'name'");
    }

    @Test
    public void testCheckStringValidityInvalidString() throws Exception {
        Method method = StickerPackValidator.class.getDeclaredMethod("checkStringValidity", String.class);
        method.setAccessible(true);

        try {
            method.invoke(null, "invalid/identifier@#$");
            fail("Expected IllegalStateException for invalid characters");
        } catch (Exception e) {
            Throwable cause = e.getCause();
            assertTrue("Expected IllegalStateException, got: " + cause, cause instanceof IllegalStateException);
        }
    }

    @Test
    public void testIsValidWebsiteUrl() throws Exception {
        Method method = StickerPackValidator.class.getDeclaredMethod("isValidWebsiteUrl", String.class);
        method.setAccessible(true);

        assertTrue((Boolean) method.invoke(null, "http://play.google.com/store/apps"));
        assertTrue((Boolean) method.invoke(null, "https://itunes.apple.com/app"));
        assertFalse((Boolean) method.invoke(null, "ftp://example.com"));
        assertFalse((Boolean) method.invoke(null, "not_a_url"));
    }
}
