package com.blurfing.app.model

import android.graphics.Bitmap

enum class ExportFormat(val compression: Bitmap.CompressFormat, val mimeType: String, val extension: String) {
    PNG(Bitmap.CompressFormat.PNG,"image/png","png"),
    JPEG(Bitmap.CompressFormat.JPEG,"image/jpeg","jpg")
}
