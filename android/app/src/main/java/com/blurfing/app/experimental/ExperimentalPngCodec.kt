package com.blurfing.app.experimental

import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.io.OutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.MessageDigest
import java.util.Base64
import java.util.zip.CRC32
import java.util.zip.DeflaterOutputStream
import java.util.zip.Inflater
import java.util.zip.InflaterInputStream

/** Canonical sRGB8 PNG subset. Color conversion belongs to photo import, never this wire decoder. */
object ExperimentalPngCodec {
    private val signature = byteArrayOf(137.toByte(),80,78,71,13,10,26,10)
    private val hashPattern = Regex("[0-9a-f]{64}")
    fun hash(bytes: ByteArray): String = hex(MessageDigest.getInstance("SHA-256").digest(bytes))
    fun hex(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(it.toInt() and 255) }
    fun requireHash(value: String) { require(hashPattern.matches(value)) }
    data class Png(val bytes: ByteArray, val width: Int, val height: Int, val colorType: Int,
                   internal val idats: List<IntRange>)

    private fun unsigned(bytes: ByteArray, at: Int): Long {
        require(at >= 0 && at.toLong()+4 <= bytes.size)
        return (0..3).fold(0L) { v,i -> (v shl 8) or (bytes[at+i].toLong() and 255) }
    }
    fun parse(bytes: ByteArray, expectedColorType: Int): Png {
        require(expectedColorType == 0 || expectedColorType == 2)
        require(bytes.size in 1..ExperimentalPhotoMemory.MAX_PNG_BYTES)
        require(bytes.size >= 45 && bytes.copyOfRange(0,8).contentEquals(signature))
        var at=8; var width=0; var height=0; var chunks=0; var ended=false; var seenIdat=false; var seenExif=false
        val idats=mutableListOf<IntRange>()
        while(at < bytes.size) {
            require(++chunks <= 4096 && at.toLong()+12 <= bytes.size)
            val length=unsigned(bytes,at); require(length <= Int.MAX_VALUE && at.toLong()+12+length <= bytes.size)
            val n=length.toInt(); val type=bytes.copyOfRange(at+4,at+8).toString(Charsets.US_ASCII)
            require(type.length==4 && type.all { it in 'A'..'Z' || it in 'a'..'z' })
            require(type[2] in 'A'..'Z') // PNG reserved bit must be zero.
            val crc=CRC32(); crc.update(bytes,at+4,n+4); require(crc.value==unsigned(bytes,at+8+n))
            val start=at+8
            if(chunks==1) require(type=="IHDR")
            when(type) {
                "IHDR" -> {
                    require(chunks==1 && n==13)
                    val w=unsigned(bytes,start);val h=unsigned(bytes,start+4)
                    require(w in 1..Int.MAX_VALUE.toLong() && h in 1..Int.MAX_VALUE.toLong())
                    width=w.toInt();height=h.toInt();ExperimentalPhotoMemory.dimensions(width,height)
                    require(bytes[start+8].toInt()==8 && bytes[start+9].toInt()==expectedColorType)
                    require(bytes[start+10].toInt()==0 && bytes[start+11].toInt()==0 && bytes[start+12].toInt()==0)
                }
                "IDAT" -> {
                    require(width>0 && !ended)
                    seenIdat=true
                    if(n>0) idats.add(start until start+n)
                }
                "IEND" -> { require(n==0 && seenIdat && !ended);ended=true;require(at+12==bytes.size) }
                "eXIf" -> { require(!seenIdat && !seenExif);seenExif=true;requireExifOne(bytes,start,n) }
                "acTL","fcTL","fdAT","tRNS" -> throw IllegalArgumentException("transparent or animated PNG is not supported")
                "iCCP","cICP","gAMA","cHRM","mDCV","cLLI","sRGB","sBIT" ->
                    throw IllegalArgumentException("canonical PNG must contain normalized sRGB pixels without color metadata")
                else -> throw IllegalArgumentException("chunk outside canonical PNG subset")
            }
            at+=n+12
        }
        require(ended && idats.isNotEmpty() && at==bytes.size)
        return Png(bytes,width,height,expectedColorType,idats)
    }
    private fun requireExifOne(bytes: ByteArray, start: Int, size: Int) {
        require(size==26)
        val little=bytes[start]=='I'.code.toByte() && bytes[start+1]=='I'.code.toByte()
        val big=bytes[start]=='M'.code.toByte() && bytes[start+1]=='M'.code.toByte()
        require(little || big)
        fun short(offset: Int): Int {
            require(offset>=0 && offset.toLong()+2<=size)
            val a=bytes[start+offset].toInt() and 255;val b=bytes[start+offset+1].toInt() and 255
            return if(little) a or (b shl 8) else (a shl 8) or b
        }
        fun int(offset: Int): Long {
            require(offset>=0 && offset.toLong()+4<=size)
            return if(little) (0..3).fold(0L) { v,i -> v or ((bytes[start+offset+i].toLong() and 255) shl (8*i)) }
            else unsigned(bytes,start+offset)
        }
        require(short(2)==42)
        require(int(4)==8L && short(8)==1 && short(10)==274 && short(12)==3 && int(14)==1L)
        require(short(18)==1 && short(20)==0 && int(22)==0L)
    }
    private class IdatStream(private val png: Png): InputStream() {
        private var chunk=0
        private var at=png.idats[0].first
        private var consumed=0
        val remainingBytes: Long get() = png.idats.sumOf { it.last.toLong()-it.first+1 }-consumed
        override fun read(): Int {
            while(chunk<png.idats.size && at>png.idats[chunk].last) {
                chunk++
                if(chunk<png.idats.size) at=png.idats[chunk].first
            }
            return if(chunk==png.idats.size) -1 else { consumed++;png.bytes[at++].toInt() and 255 }
        }
        override fun read(b: ByteArray, off: Int, len: Int): Int {
            if(len==0)return 0
            var n=0
            while(n<len) { val value=read();if(value<0)break;b[off+n++]=value.toByte() }
            return if(n==0)-1 else n
        }
    }
    private fun paeth(a: Int,b: Int,c: Int): Int {
        val p=a+b-c;val da=kotlin.math.abs(p-a);val db=kotlin.math.abs(p-b);val dc=kotlin.math.abs(p-c)
        return if(da<=db && da<=dc)a else if(db<=dc)b else c
    }
    /** Two row buffers, so two PNGs can be compared without two full Bitmaps. */
    class RowReader internal constructor(private val png: Png, private val checkActive: ()->Unit): java.io.Closeable {
        val bpp=if(png.colorType==2)3 else 1
        val length=Math.multiplyExact(png.width,bpp);var previous=ByteArray(length);var current=ByteArray(length)
        val inflater=Inflater()
        private val idat=IdatStream(png)
        private val input=InflaterInputStream(idat,inflater)
        private var y=0
        fun next(): ByteArray {
                    require(y++<png.height)
                    checkActive()
                    val filter=input.read(); require(filter in 0..4)
                    var got=0
                    while(got<length) { val n=input.read(current,got,length-got);require(n>0);got+=n }
                    for(x in current.indices) {
                        val a=if(x>=bpp)current[x-bpp].toInt() and 255 else 0
                        val b=previous[x].toInt() and 255
                        val c=if(x>=bpp)previous[x-bpp].toInt() and 255 else 0
                        val predictor=when(filter) { 0->0;1->a;2->b;3->(a+b)/2;else->paeth(a,b,c) }
                        current[x]=((current[x].toInt() and 255)+predictor).toByte()
                    }
                    val swap=previous;previous=current;current=swap
                    return previous
        }
        fun finish() { require(y==png.height && input.read()==-1 && inflater.finished() && inflater.remaining==0 && idat.remainingBytes==0L) }
        override fun close() { try { input.close() } finally { inflater.end() } }
    }
    fun rowReader(png: Png,checkActive: ()->Unit = {})=RowReader(png,checkActive)
    /** Reuses row buffers. Callback must consume the row before returning. */
    fun rows(png: Png, checkActive: () -> Unit = {}, row: (Int,ByteArray)->Unit) {
        rowReader(png,checkActive).use { reader -> repeat(png.height) { y -> row(y,reader.next()) };reader.finish() }
    }
    private class LimitedBytes: ByteArrayOutputStream() {
        override fun write(b: Int) { require(count<ExperimentalPhotoMemory.MAX_PNG_BYTES);super.write(b) }
        override fun write(b: ByteArray, off: Int, len: Int) {
            require(count.toLong()+len<=ExperimentalPhotoMemory.MAX_PNG_BYTES);super.write(b,off,len)
        }
    }
    private fun chunk(output: OutputStream, type: String, data: ByteArray) {
        output.write(ByteBuffer.allocate(4).putInt(data.size).array());val t=type.toByteArray(Charsets.US_ASCII)
        output.write(t);output.write(data);val crc=CRC32();crc.update(t);crc.update(data)
        output.write(ByteBuffer.allocate(4).putInt(crc.value.toInt()).array())
    }
    data class Encoded(val png: ByteArray, val rgbSha256: String)
    fun encodeRgb(width: Int,height: Int,checkActive: ()->Unit = {}, rowProvider: (Int,ByteArray)->Unit): Encoded {
        ExperimentalPhotoMemory.dimensions(width,height)
        val digest=MessageDigest.getInstance("SHA-256");val row=ByteArray(Math.multiplyExact(width,3))
        val previous=ByteArray(row.size);val candidate=ByteArray(row.size);val best=ByteArray(row.size)
        val output=LimitedBytes();output.write(signature)
        val ihdr=ByteBuffer.allocate(13).order(ByteOrder.BIG_ENDIAN).putInt(width).putInt(height).put(8).put(2).put(0).put(0).put(0).array()
        chunk(output,"IHDR",ihdr)
        // Stream consecutive IDAT chunks instead of retaining a second full compressed raster.
        val idat=object: OutputStream() {
            val buffer=ByteArray(64*1024);var count=0
            override fun write(value: Int) { buffer[count++]=value.toByte();if(count==buffer.size)flush() }
            override fun write(bytes: ByteArray,off: Int,len: Int) {
                var p=off;var remaining=len
                while(remaining>0) { val n=minOf(remaining,buffer.size-count);bytes.copyInto(buffer,count,p,p+n);count+=n;p+=n;remaining-=n;if(count==buffer.size)flush() }
            }
            override fun flush() { if(count>0) { chunk(output,"IDAT",buffer.copyOf(count));count=0 } }
            override fun close()=flush()
        }
        DeflaterOutputStream(idat).use { zip ->
            repeat(height) { y ->
                checkActive();rowProvider(y,row);digest.update(row)
                var bestScore=Long.MAX_VALUE;var bestFilter=0
                // PNG's reversible row filters improve size; they never alter decoded RGB.
                repeat(5) { filter ->
                    var score=0L
                    for(x in row.indices) {
                        val a=if(x>=3)row[x-3].toInt() and 255 else 0
                        val b=previous[x].toInt() and 255
                        val c=if(x>=3)previous[x-3].toInt() and 255 else 0
                        val prediction=when(filter) { 0->0;1->a;2->b;3->(a+b)/2;else->paeth(a,b,c) }
                        val residual=((row[x].toInt() and 255)-prediction).toByte()
                        candidate[x]=residual;score+=kotlin.math.abs(residual.toInt())
                    }
                    if(score<bestScore) { bestScore=score;bestFilter=filter;candidate.copyInto(best) }
                }
                zip.write(bestFilter);zip.write(best);row.copyInto(previous)
            }
        }
        chunk(output,"IEND",byteArrayOf())
        return Encoded(output.toByteArray(),hex(digest.digest()))
    }
    fun base64(value: String): ByteArray {
        val maxChars=4L*((ExperimentalPhotoMemory.MAX_PNG_BYTES+2L)/3)
        require(value.isNotEmpty() && value.length.toLong()<=maxChars && value.length%4==0)
        val alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        var padding=0
        value.forEachIndexed { i,c ->
            if(c=='=') { padding++;require(i>=value.length-2 && padding<=2) }
            else require(padding==0 && alphabet.indexOf(c)>=0)
        }
        if(padding==2) require((alphabet.indexOf(value[value.length-3]) and 15)==0)
        if(padding==1) require((alphabet.indexOf(value[value.length-2]) and 3)==0)
        return Base64.getDecoder().decode(value).also { require(it.size in 1..ExperimentalPhotoMemory.MAX_PNG_BYTES) }
    }
}
