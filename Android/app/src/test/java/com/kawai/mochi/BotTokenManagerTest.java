package com.kawai.mochi;

import org.junit.Test;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public class BotTokenManagerTest {

    @Test
    public void testIsValidTokenFormat() {
        assertTrue(BotTokenManager.isValidTokenFormat("123456789:ABCdefGHIjklMNOpqrsTUVwxyz"));
        assertTrue(BotTokenManager.isValidTokenFormat("987654321:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"));

        assertFalse(BotTokenManager.isValidTokenFormat(null));
        assertFalse(BotTokenManager.isValidTokenFormat(""));
        assertFalse(BotTokenManager.isValidTokenFormat("invalid_token_no_colon"));
        assertFalse(BotTokenManager.isValidTokenFormat("not_a_number:ABCdefGHIjklMNOpqrs"));
        assertFalse(BotTokenManager.isValidTokenFormat("123456:short"));
    }

    @Test
    public void testRedactBotToken() {
        String input = "GET https://api.telegram.org/bot123456789:ABCdefGHIjklMNOpqrs/getStickerSet → 200";
        String redacted = TelegramApiClient.redactBotToken(input);
        assertFalse(redacted.contains("123456789:ABCdefGHIjklMNOpqrs"));
        assertTrue(redacted.contains("bot***"));

        String fileInput = "GET https://api.telegram.org/file/bot987654321:XYZsecretToken12345678/photos/1.jpg → 200";
        String fileRedacted = TelegramApiClient.redactBotToken(fileInput);
        assertFalse(fileRedacted.contains("987654321:XYZsecretToken12345678"));
        assertTrue(fileRedacted.contains("file/bot***"));
    }
}
