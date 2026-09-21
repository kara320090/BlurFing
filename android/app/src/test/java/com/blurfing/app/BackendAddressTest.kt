package com.blurfing.app

import com.blurfing.app.repository.BackendAddress
import org.junit.Assert.*
import org.junit.Test

class BackendAddressTest {
    @Test fun acceptsHttpsAndNormalizesTrailingSlash() {
        assertEquals("https://demo.example.org/api",
            BackendAddress.normalize(" https://demo.example.org/api/ ", false))
    }
    @Test fun localHttpOnlyWorksInDevelopment() {
        assertEquals("http://10.0.2.2:8000",
            BackendAddress.normalize("http://10.0.2.2:8000/", true))
        assertThrows(IllegalArgumentException::class.java) {
            BackendAddress.normalize("http://10.0.2.2:8000", false)
        }
        assertThrows(IllegalArgumentException::class.java) {
            BackendAddress.normalize("http://example.org", true)
        }
    }
    @Test fun rejectsInvalidOrCredentialBearingAddresses() {
        listOf("", "example.org", "https://user:secret@example.org", "https://example.org?key=x",
            "https://example.org#fragment").forEach { value ->
            assertThrows(value, IllegalArgumentException::class.java) {
                BackendAddress.normalize(value, true)
            }
        }
    }
}
