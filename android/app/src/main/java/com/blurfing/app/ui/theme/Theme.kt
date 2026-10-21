package com.blurfing.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val LightColors = lightColorScheme(
    primary = Color(0xFF087480), onPrimary = Color.White,
    primaryContainer = Color(0xFFE0F1F2), onPrimaryContainer = Color(0xFF06444C),
    secondary = Color(0xFF526F80), onSecondary = Color.White,
    secondaryContainer = Color(0xFFE5EEF2), onSecondaryContainer = Color(0xFF263F4E),
    tertiary = Color(0xFF916D2C), onTertiary = Color.White,
    tertiaryContainer = Color(0xFFFFF0CE), onTertiaryContainer = Color(0xFF6A4A13),
    background = Color(0xFFF0F5F7), onBackground = Color(0xFF142E3B),
    surface = Color.White, onSurface = Color(0xFF142E3B),
    surfaceVariant = Color(0xFFE9F0F3), onSurfaceVariant = Color(0xFF526C7A),
    outline = Color(0xFF738B97), outlineVariant = Color(0xFFD9E5E9),
    error = Color(0xFFB33E45), onError = Color.White,
    errorContainer = Color(0xFFFFECEC), onErrorContainer = Color(0xFF77272D),
)
private val DarkColors = darkColorScheme(
    primary = Color(0xFF78D2D6), onPrimary = Color(0xFF00383E),
    primaryContainer = Color(0xFF10464D), onPrimaryContainer = Color(0xFFD5F3F4),
    secondary = Color(0xFFB1CAD7), onSecondary = Color(0xFF203B48),
    secondaryContainer = Color(0xFF304F5D), onSecondaryContainer = Color(0xFFE0EFF5),
    tertiary = Color(0xFFEAC986), onTertiary = Color(0xFF49340A),
    tertiaryContainer = Color(0xFF58431B), onTertiaryContainer = Color(0xFFFFE9B7),
    background = Color(0xFF101E25), onBackground = Color(0xFFE7F2F5),
    surface = Color(0xFF192C36), onSurface = Color(0xFFE7F2F5),
    surfaceVariant = Color(0xFF243C47), onSurfaceVariant = Color(0xFFB2C5CF),
    outline = Color(0xFF8DA5B1), outlineVariant = Color(0xFF38515C),
    error = Color(0xFFFFB3B7), onError = Color(0xFF661B23),
    errorContainer = Color(0xFF662C33), onErrorContainer = Color(0xFFFFE3E4),
)
private fun type(size: Int, line: Int, weight: FontWeight = FontWeight.Normal) =
    TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = weight, fontSize = size.sp, lineHeight = line.sp)
private val AppTypography = Typography(
    headlineLarge = type(32, 42, FontWeight.Bold),
    headlineMedium = type(28, 38, FontWeight.Bold),
    headlineSmall = type(24, 34, FontWeight.Bold),
    titleLarge = type(21, 30, FontWeight.SemiBold),
    titleMedium = type(17, 25, FontWeight.SemiBold),
    titleSmall = type(14, 22, FontWeight.SemiBold),
    bodyLarge = type(16, 26), bodyMedium = type(14, 23), bodySmall = type(12, 20),
    labelLarge = type(14, 22, FontWeight.SemiBold),
    labelMedium = type(12, 18, FontWeight.Medium),
)
@Composable
fun BlurFingTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors, typography = AppTypography,
        shapes = Shapes(extraSmall = RoundedCornerShape(8.dp), small = RoundedCornerShape(12.dp),
            medium = RoundedCornerShape(16.dp), large = RoundedCornerShape(22.dp), extraLarge = RoundedCornerShape(28.dp)),
        content = content,
    )
}
