package com.kawai.mochi;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;

public class AddStickerPackLaunchLogicTest {

    public static String determineTargetPackage(
            boolean consumerInstalled,
            boolean smbInstalled,
            boolean consumerWhitelisted,
            boolean smbWhitelisted
    ) {
        if (!consumerInstalled && !smbInstalled) {
            return null; // Fallback to chooser
        }

        if (consumerInstalled && smbInstalled) {
            if (!consumerWhitelisted && !smbWhitelisted) return null; // Chooser
            if (!consumerWhitelisted) return WhitelistCheck.CONSUMER_WHATSAPP_PACKAGE_NAME;
            if (!smbWhitelisted) return WhitelistCheck.SMB_WHATSAPP_PACKAGE_NAME;
            return null; // Both whitelisted -> chooser
        }

        if (consumerInstalled) {
            return WhitelistCheck.CONSUMER_WHATSAPP_PACKAGE_NAME;
        }

        return WhitelistCheck.SMB_WHATSAPP_PACKAGE_NAME;
    }

    @Test
    public void testConsumerInstalledWhitelistedAndSmbNotInstalled() {
        // Case: Consumer installed & already whitelisted, SMB not installed at all
        String target = determineTargetPackage(
                true,   // consumerInstalled
                false,  // smbInstalled
                true,   // consumerWhitelisted
                false   // smbWhitelisted (returns false because SMB is not installed)
        );

        // MUST target com.whatsapp (installed package), NEVER com.whatsapp.w4b
        assertEquals("Target package should be consumer WhatsApp", WhitelistCheck.CONSUMER_WHATSAPP_PACKAGE_NAME, target);
    }

    @Test
    public void testSmbInstalledWhitelistedAndConsumerNotInstalled() {
        // Case: SMB installed & already whitelisted, Consumer not installed at all
        String target = determineTargetPackage(
                false,  // consumerInstalled
                true,   // smbInstalled
                false,  // consumerWhitelisted
                true    // smbWhitelisted
        );

        // MUST target com.whatsapp.w4b (installed package), NEVER com.whatsapp
        assertEquals("Target package should be WhatsApp SMB", WhitelistCheck.SMB_WHATSAPP_PACKAGE_NAME, target);
    }

    @Test
    public void testNeitherInstalled() {
        String target = determineTargetPackage(false, false, false, false);
        assertNull("Target package should be null for chooser fallback when neither is installed", target);
    }
}
