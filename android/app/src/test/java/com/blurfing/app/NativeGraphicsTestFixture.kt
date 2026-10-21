package com.blurfing.app

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Rect

/**
 * A ViewModel test has no Activity drawing before its first image operation. Initialize Robolectric's
 * native Canvas/Paint in fixture setup, outside the coroutine deadline that guards the workflow.
 * Real Android has already drawn the Activity; this is not an app/device performance measurement.
 */
internal fun prepareNativeGraphicsFixture() {
    val source = Bitmap.createBitmap(2,2,Bitmap.Config.ARGB_8888)
    val target = Bitmap.createBitmap(2,2,Bitmap.Config.ARGB_8888)
    try { Canvas(target).drawBitmap(source,null,Rect(0,0,2,2),Paint(Paint.FILTER_BITMAP_FLAG)) }
    finally { source.recycle(); target.recycle() }
}
