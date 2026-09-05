package com.veyra.cs3runtime

import android.app.Activity
import android.os.Bundle
import dalvik.system.DexClassLoader
import dalvik.system.DexFile
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.suspendCancellableCoroutine
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.File
import java.io.InputStreamReader
import java.net.ServerSocket
import java.net.Socket
import java.util.zip.ZipFile
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.coroutines.suspendCoroutine

class MainActivity : Activity() {
    private var server: ServerSocket? = null
    private var worker: Thread? = null
    private var loadedPackage: String? = null
    private var provider: Any? = null

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        val packagePath = intent.getStringExtra("package_path")
        val port = intent.getIntExtra("port", 18787)
        if (packagePath != null) {
            loadedPackage = packagePath
            provider = loadProvider(packagePath)
        }
        startServer(port)
    }

    private fun startServer(port: Int) {
        worker = Thread {
            server = ServerSocket(port, 8, java.net.InetAddress.getByName("127.0.0.1"))
            while (!server!!.isClosed) {
                try {
                    server!!.accept().use { socket -> handle(socket) }
                } catch (_: Exception) {
                    if (server?.isClosed != true) continue
                }
            }
        }.also { it.start() }
    }

    private fun handle(socket: Socket) {
        val reader = BufferedReader(InputStreamReader(socket.getInputStream(), Charsets.UTF_8))
        val line = reader.readLine() ?: return
        val request = JSONObject(line)
        val response = try {
            dispatch(request)
        } catch (t: Throwable) {
            JSONObject().put("error", t.message ?: t.javaClass.name)
        }
        socket.getOutputStream().use { out ->
            out.write((response.toString() + "\n").toByteArray(Charsets.UTF_8))
            out.flush()
        }
    }

    private fun dispatch(request: JSONObject): JSONObject {
        require(request.optInt("protocol", 0) == 1) { "unsupported protocol" }
        return when (request.optString("method")) {
            "health" -> JSONObject()
                .put("protocol", 1)
                .put("runtime", "veyra-android-art-cs3")
                .put("dex_execution", true)
                .put("android_api_bridge", true)
                .put("cloudstream_api_bridge", true)
            "providers" -> providersResponse()
            "home" -> invokeProvider("getMainPage", request.optJSONObject("payload") ?: JSONObject())
            "search" -> invokeProvider("search", request.optJSONObject("payload") ?: JSONObject())
            "load" -> invokeProvider("load", request.optJSONObject("payload") ?: JSONObject())
            "loadLinks" -> invokeProvider("loadLinks", request.optJSONObject("payload") ?: JSONObject())
            "streams" -> invokeProvider("loadLinks", request.optJSONObject("payload") ?: JSONObject())
            else -> throw IllegalArgumentException("unsupported method")
        }
    }

    private fun providersResponse(): JSONObject {
        val p = provider ?: throw IllegalStateException("no MainAPI provider found")
        return JSONObject().put("providers", JSONArray().put(JSONObject()
            .put("name", readProperty(p, "name") ?: p.javaClass.simpleName)
            .put("internalName", p.javaClass.name)
            .put("mainUrl", readProperty(p, "mainUrl") ?: "")
            .put("language", readProperty(p, "lang") ?: "en")
        ))
    }

    private fun invokeProvider(name: String, payload: JSONObject): JSONObject = runBlocking {
        val p = provider ?: throw IllegalStateException("no MainAPI provider found")
        when (name) {
            "search" -> {
                val result = invokeSuspend(p, "search", listOf(payload.optString("query")))
                JSONObject().put("items", toSearchArray(result))
            }
            "load" -> {
                val result = invokeSuspend(p, "load", listOf(payload.optString("url")))
                JSONObject().put("load", toLoadObject(result))
            }
            "loadLinks", "streams" -> {
                val streams = JSONArray()
                val callback: (Any?) -> Unit = { value -> streams.put(toStreamObject(value)) }
                val args = buildLoadLinksArgs(p, payload.optString("url"), callback)
                invokeSuspend(p, "loadLinks", args)
                JSONObject().put("streams", streams)
            }
            "getMainPage" -> {
                val page = payload.optInt("page", 1)
                val result = invokeSuspend(p, "getMainPage", listOf(page, null))
                JSONObject().put("homePages", toHomeArray(result))
            }
            else -> throw IllegalArgumentException("unsupported provider method")
        }
    }

    private fun buildLoadLinksArgs(provider: Any, data: String, callback: (Any?) -> Unit): List<Any?> {
        val method = provider.javaClass.methods.firstOrNull { it.name == "loadLinks" && it.parameterTypes.any { p -> p.name == "kotlin.coroutines.Continuation" } }
            ?: throw NoSuchMethodException("loadLinks")
        val args = mutableListOf<Any?>()
        var functionIndex = 0
        method.parameterTypes.dropLast(1).forEach { type ->
            when {
                type == String::class.java -> args += data
                type == Boolean::class.javaPrimitiveType || type == Boolean::class.javaObjectType -> args += false
                type.name == "kotlin.jvm.functions.Function1" -> {
                    args += if (functionIndex++ == 0) ({ _: Any? -> Unit }) else callback
                }
                else -> args += null
            }
        }
        return args
    }

    private suspend fun invokeSuspend(receiver: Any, methodName: String, args: List<Any?>): Any? {
        val method = receiver.javaClass.methods.firstOrNull {
            it.name == methodName && it.parameterTypes.lastOrNull()?.name == "kotlin.coroutines.Continuation"
        } ?: throw NoSuchMethodException(methodName)
        return suspendCancellableCoroutine { continuation ->
            try {
                val full = args.toMutableList()
                full += continuation
                val result = method.invoke(receiver, *full.toTypedArray())
                if (result !== kotlin.coroutines.intrinsics.COROUTINE_SUSPENDED) {
                    continuation.resume(result)
                }
            } catch (t: Throwable) {
                continuation.resumeWithException(t.cause ?: t)
            }
        }
    }

    private fun loadProvider(packagePath: String): Any {
        val packageFile = File(packagePath)
        require(packageFile.isFile) { "CS3 package does not exist" }
        val id = packageFile.nameWithoutExtension
        val dir = File(filesDir, "cs3/$id").apply { mkdirs() }
        val dex = File(dir, "classes.dex")
        ZipFile(packageFile).use { zip ->
            val entry = zip.getEntry("classes.dex") ?: throw IllegalArgumentException("CS3 has no classes.dex")
            zip.getInputStream(entry).use { input -> dex.outputStream().use { output -> input.copyTo(output) } }
        }
        val optimized = File(dir, "optimized").apply { mkdirs() }
        val loader = DexClassLoader(dex.absolutePath, optimized.absolutePath, null, classLoader)
        val dexFile = DexFile(dex.absolutePath)
        dexFile.entries().asSequence().forEach { className ->
            try {
                val clazz = Class.forName(className, false, loader)
                if (isMainApi(clazz)) {
                    val constructor = clazz.getDeclaredConstructor().apply { isAccessible = true }
                    return constructor.newInstance()
                }
            } catch (_: Throwable) {
                // One broken optional class must not prevent provider discovery.
            }
        }
        throw IllegalStateException("No CloudStream MainAPI implementation found in CS3")
    }

    private fun isMainApi(clazz: Class<*>): Boolean {
        var current: Class<*>? = clazz
        while (current != null) {
            if (current.name == "com.lagradost.cloudstream3.MainAPI") return true
            current = current.superclass
        }
        return false
    }

    private fun toSearchArray(value: Any?): JSONArray {
        val array = JSONArray()
        (value as? Iterable<*>)?.forEach { item -> array.put(toSearchObject(item)) }
        return array
    }

    private fun toHomeArray(value: Any?): JSONArray {
        val array = JSONArray()
        val pages = readProperty(value, "items") ?: readProperty(value, "pages")
        (pages as? Iterable<*>)?.forEach { page ->
            array.put(JSONObject().put("name", readProperty(page, "name") ?: "Home").put("items", toSearchArray(readProperty(page, "list"))))
        }
        return array
    }

    private fun toSearchObject(value: Any?): JSONObject = JSONObject()
        .put("title", readProperty(value, "name") ?: readProperty(value, "title") ?: "")
        .put("url", readProperty(value, "url") ?: readProperty(value, "data") ?: "")
        .put("poster", readProperty(value, "posterUrl") ?: JSONObject.NULL)
        .put("year", readProperty(value, "year") ?: JSONObject.NULL)
        .put("type", readProperty(value, "type")?.toString() ?: "unknown")

    private fun toLoadObject(value: Any?): JSONObject = JSONObject()
        .put("title", readProperty(value, "name") ?: "")
        .put("url", readProperty(value, "url") ?: "")
        .put("poster", readProperty(value, "posterUrl") ?: JSONObject.NULL)
        .put("plot", readProperty(value, "plot") ?: JSONObject.NULL)
        .put("year", readProperty(value, "year") ?: JSONObject.NULL)

    private fun toStreamObject(value: Any?): JSONObject = JSONObject()
        .put("url", readProperty(value, "url") ?: "")
        .put("quality", readProperty(value, "quality") ?: -1)
        .put("referer", readProperty(value, "referer") ?: "")
        .put("headers", JSONObject(readProperty(value, "headers")?.toString() ?: "{}"))
        .put("type", readProperty(value, "type")?.toString() ?: "video")

    private fun readProperty(value: Any?, name: String): Any? {
        if (value == null) return null
        val cap = name.replaceFirstChar { it.uppercase() }
        try { return value.javaClass.methods.firstOrNull { it.name == "get$cap" && it.parameterCount == 0 }?.invoke(value) } catch (_: Throwable) {}
        try { return value.javaClass.methods.firstOrNull { it.name == name && it.parameterCount == 0 }?.invoke(value) } catch (_: Throwable) {}
        try { return value.javaClass.getDeclaredField(name).apply { isAccessible = true }.get(value) } catch (_: Throwable) {}
        return null
    }

    override fun onDestroy() {
        server?.close()
        worker?.interrupt()
        super.onDestroy()
    }
}
