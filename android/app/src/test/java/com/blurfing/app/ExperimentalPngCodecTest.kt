package com.blurfing.app.experimental

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.File

class ExperimentalPngCodecTest {
    private fun fixture(name: String)=javaClass.getResourceAsStream("/experimental-png/$name")!!.use { it.readBytes() }
    private fun rejects(block: ()->Unit) { try { block();fail("Invalid PNG was accepted") } catch(_: IllegalArgumentException) { } catch(_: java.io.IOException) { } }
    @Test fun parallelDeflateFullFlushBlocksDecodeAsOneStream() {
        val png=ExperimentalPngCodec.parse(fixture("RGB-parallel-deflate.png"),2)
        val decoded=ByteArrayOutputStream()
        ExperimentalPngCodec.rows(png) { _,row -> decoded.write(row) }
        val expected=ArrayList<Byte>()
        repeat(7) { y -> repeat(9) { x ->
            listOf((x*29+y*7)%256,(x*11+y*31)%256,(x*43+y*17)%256).forEach { expected.add(it.toByte()) }
        } }
        assertArrayEquals(expected.toByteArray(),decoded.toByteArray())
    }
    @Test fun allFiveFiltersAndPillowFilesMatchIndependentPixelsAndSha() {
        val manifest=JSONObject(fixture("manifest.json").toString(Charsets.UTF_8))
        for(mode in listOf("RGB","L")) for(ending in (0..4).map { "filter$it" }+"pillow") {
            val name="$mode-$ending.png";val bytes=fixture(name);val expected=manifest.getJSONObject(name)
            assertEquals(expected.getString("png_sha256"),ExperimentalPngCodec.hash(bytes))
            val png=ExperimentalPngCodec.parse(bytes,if(mode=="RGB")2 else 0);val pixels=ByteArrayOutputStream()
            ExperimentalPngCodec.rows(png) { _,row -> pixels.write(row) }
            val raw=pixels.toByteArray()
            assertEquals(expected.getString("pixel_sha256"),ExperimentalPngCodec.hash(raw))
            val pattern=ArrayList<Byte>()
            repeat(7) { y -> repeat(9) { x -> if(mode=="RGB")listOf((x*29+y*7)%256,(x*11+y*31)%256,(x*43+y*17)%256).forEach { pattern.add(it.toByte()) }
                else pattern.add(if((x+y)%3==0)255.toByte() else 0) } }
            assertArrayEquals(pattern.toByteArray(),raw)
        }
    }
    @Test fun malformedUnsupportedTruncatedAndInflationBombContractsReject() {
        val invalid=JSONObject(fixture("manifest.json").toString(Charsets.UTF_8)).getJSONArray("invalid_names")
        repeat(invalid.length()) { i -> val name=invalid.getString(i)
            rejects { ExperimentalPngCodec.rows(ExperimentalPngCodec.parse(fixture("invalid-$name.png"),2)) { _,_-> } }
        }
    }
    @Test fun canonicalMinimalLittleEndianAndPillowBigEndianExifHaveTheSamePixels() {
        fun raw(name: String): ByteArray { val output=ByteArrayOutputStream();ExperimentalPngCodec.rows(ExperimentalPngCodec.parse(fixture(name),2)) { _,row -> output.write(row) };return output.toByteArray() }
        assertArrayEquals(raw("RGB-pillow.png"),raw("RGB-little-exif.png"))
    }
    @Test fun base64RejectsAmbiguousPaddingWhitespaceAndOversize() {
        for(value in listOf("","A===","AAAA=","AA=A","AB==","AAB=","AA==\n","!!!!"))rejects { ExperimentalPngCodec.base64(value) }
        assertArrayEquals(byteArrayOf(0),ExperimentalPngCodec.base64("AA=="))
        rejects { ExperimentalPngCodec.base64("A".repeat(4*((ExperimentalPhotoMemory.MAX_PNG_BYTES+2)/3)+4)) }
    }
    @Test fun encoderProducesIndependentPillowCrosscheckArtifact() {
        val encoded=ExperimentalPngCodec.encodeRgb(9,7) { y,row -> repeat(9) { x ->
            row[3*x]=((x*29+y*7)%256).toByte();row[3*x+1]=((x*11+y*31)%256).toByte();row[3*x+2]=((x*43+y*17)%256).toByte()
        } }
        val out=File(System.getenv("BLURFING_CODEC_CROSSCHECK_DIR") ?: "build/codec-cross-check").apply { mkdirs() }
        File(out,"kotlin-encoded-synthetic.png").writeBytes(encoded.png)
        File(out,"kotlin-encoded-synthetic.rgb.sha256").writeText(encoded.rgbSha256)
        assertEquals(2,ExperimentalPngCodec.parse(encoded.png,2).colorType)
    }
    @Test fun optionalPrivateFullResolutionPillowSourceCrosscheckNoPhotoBundled() {
        val path=System.getenv("BLURFING_PRIVATE_PNG");val hash=System.getenv("BLURFING_PRIVATE_RGB_SHA")
        assumeTrue(path!=null && hash!=null)
        val bytes=File(path!!).readBytes();val png=ExperimentalPngCodec.parse(bytes,2)
        val digest=java.security.MessageDigest.getInstance("SHA-256");var rows=0
        ExperimentalPngCodec.rows(png) { _,row -> rows++;digest.update(row) }
        assertEquals(png.height,rows);assertEquals(hash,ExperimentalPngCodec.hex(digest.digest()))
    }
    @Test fun fullResolutionMemoryPlansAreBoundedAndNeverDownscale() {
        assertEquals(12_192_768L,ExperimentalPhotoMemory.dimensions(4032,3024))
        assertTrue(ExperimentalPhotoMemory.upload(4032,3024).peakBytes<224L*1024*1024)
        ExperimentalPhotoMemory.requireAvailable(ExperimentalPhotoMemory.upload(4032,3024),256L*1024*1024,64L*1024*1024)
        try { ExperimentalPhotoMemory.requireAvailable(ExperimentalPhotoMemory.upload(5000,4000),192L*1024*1024,160L*1024*1024);fail() } catch(_: ExperimentalPhotoException) { }
        rejects { ExperimentalPhotoMemory.dimensions(Int.MAX_VALUE,Int.MAX_VALUE) }
        rejects { ExperimentalPhotoMemory.dimensions(0,1) }
        val mask=CompactPermissionMask(4032,3024);assertEquals((12_192_768+7)/8,mask.storageBytes)
    }
}
