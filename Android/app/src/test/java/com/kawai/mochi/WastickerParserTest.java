package com.kawai.mochi;

import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.Method;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

public class WastickerParserTest {

    @Rule
    public TemporaryFolder temporaryFolder = new TemporaryFolder();

    @Test
    public void testZipSlipVulnerabilityPrevention() throws Exception {
        File destDir = temporaryFolder.newFolder("zip_dest");
        File evilFile = new File(destDir.getParentFile(), "evil.txt");
        if (evilFile.exists()) evilFile.delete();

        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        try (ZipOutputStream zos = new ZipOutputStream(bos)) {
            zos.putNextEntry(new ZipEntry("../../evil.txt"));
            zos.write("malicious payload".getBytes());
            zos.closeEntry();
        }

        byte[] zipBytes = bos.toByteArray();
        Method unzipMethod = WastickerParser.class.getDeclaredMethod("unzip", InputStream.class, File.class);
        unzipMethod.setAccessible(true);

        try {
            unzipMethod.invoke(null, new ByteArrayInputStream(zipBytes), destDir);
            fail("Expected InvocationTargetException containing Zip Slip IOException");
        } catch (Exception e) {
            Throwable cause = e.getCause();
            assertTrue("Expected IOException cause, got: " + cause, cause instanceof IOException);
            assertTrue("Expected path traversal message, got: " + cause.getMessage(),
                    cause.getMessage().toLowerCase().contains("path traversal"));
        }

        assertFalse("File should not have been created outside target directory!", evilFile.exists());
    }

    @Test
    public void testZipBombEntryCountLimitEnforcement() throws Exception {
        File destDir = temporaryFolder.newFolder("zip_bomb_entries_dest");

        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        try (ZipOutputStream zos = new ZipOutputStream(bos)) {
            for (int i = 0; i < 2005; i++) {
                zos.putNextEntry(new ZipEntry("file_" + i + ".txt"));
                zos.write("a".getBytes());
                zos.closeEntry();
            }
        }

        byte[] zipBytes = bos.toByteArray();
        Method unzipMethod = WastickerParser.class.getDeclaredMethod("unzip", InputStream.class, File.class);
        unzipMethod.setAccessible(true);

        try {
            unzipMethod.invoke(null, new ByteArrayInputStream(zipBytes), destDir);
            fail("Expected InvocationTargetException containing Zip Bomb entry count limit IOException");
        } catch (Exception e) {
            Throwable cause = e.getCause();
            assertTrue("Expected IOException cause, got: " + cause, cause instanceof IOException);
            assertTrue("Expected entry count error message, got: " + cause.getMessage(),
                    cause.getMessage().toLowerCase().contains("entry count")
                            || cause.getMessage().toLowerCase().contains("oversized"));
        }
    }
}
