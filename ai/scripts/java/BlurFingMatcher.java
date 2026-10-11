import com.machinezoo.sourceafis.*;
import com.google.gson.*;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.dataformat.cbor.CBORFactory;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;

public class BlurFingMatcher {
    private static final String VERSION = "3.18.1";
    private static String sha256(byte[] input) throws Exception {
        byte[] hash=MessageDigest.getInstance("SHA-256").digest(input);
        StringBuilder out=new StringBuilder();
        for(byte b:hash) out.append(String.format(Locale.ROOT,"%02x",b&255));
        return out.toString();
    }
    public static void main(String[] args) throws Exception {
        if(args.length!=3) throw new IllegalArgumentException("request.json result.json cache_dir required");
        Gson gson=new GsonBuilder().setPrettyPrinting().create();
        JsonObject request=JsonParser.parseString(Files.readString(Paths.get(args[0]),StandardCharsets.UTF_8)).getAsJsonObject();
        double dpi=request.get("dpi").getAsDouble();
        Path cache=Paths.get(args[2]);Files.createDirectories(cache);
        ObjectMapper cbor=new ObjectMapper(new CBORFactory());
        Map<String,FingerprintTemplate> templates=new HashMap<>();
        Map<String,Integer> counts=new HashMap<>();
        Map<String,FingerprintMatcher> matchers=new HashMap<>();
        JsonArray images=new JsonArray();int index=0;
        for(JsonElement element:request.getAsJsonArray("images")) {
            JsonObject item=element.getAsJsonObject();String key=item.get("key").getAsString();
            JsonObject row=new JsonObject();row.addProperty("key",key);row.addProperty("path",item.get("path").getAsString());
            long start=System.nanoTime();
            try {
                byte[] encoded=Files.readAllBytes(Paths.get(item.get("path").getAsString()));
                String hash=sha256(encoded);row.addProperty("image_sha256",hash);
                String cacheKey=sha256((hash+"|"+VERSION+"|"+dpi).getBytes(StandardCharsets.UTF_8));
                Path stored=cache.resolve(cacheKey+".cbor");FingerprintTemplate template;
                boolean cached=Files.exists(stored);row.addProperty("cached",cached);
                if(cached) template=new FingerprintTemplate(Files.readAllBytes(stored));
                else {
                    template=new FingerprintTemplate(new FingerprintImage(encoded,new FingerprintImageOptions().dpi(dpi)));
                    Files.write(stored,template.toByteArray());
                }
                byte[] serialized=template.toByteArray();JsonNode nativeTemplate=cbor.readTree(serialized);
                JsonObject metadata=JsonParser.parseString(nativeTemplate.toString()).getAsJsonObject();
                int count=metadata.getAsJsonArray("positionsX").size();
                row.addProperty("minutiae_count",count);row.addProperty("status",count>0?"ok":"no_minutiae");
                row.add("template",metadata);row.addProperty("template_sha256",sha256(serialized));
                row.addProperty("cache_key",cacheKey);templates.put(key,template);counts.put(key,count);
            } catch(Exception ex) {
                row.addProperty("status","failed");row.addProperty("error",ex.getClass().getSimpleName()+": "+ex.getMessage());
            }
            row.addProperty("extract_seconds",(System.nanoTime()-start)/1e9);images.add(row);index++;
            if(index%10==0 || index==request.getAsJsonArray("images").size()) {
                System.out.println("[SourceAFIS] templates "+index+"/"+request.getAsJsonArray("images").size());
                System.out.flush();
            }
        }
        JsonArray pairs=new JsonArray();
        for(JsonElement element:request.getAsJsonArray("pairs")) {
            JsonObject item=element.getAsJsonObject();JsonObject row=item.deepCopy();
            String probe=item.get("probe").getAsString(),candidate=item.get("candidate").getAsString();
            long start=System.nanoTime();
            try {
                if(!templates.containsKey(probe)||!templates.containsKey(candidate)) throw new IllegalStateException("Template extraction failed");
                FingerprintMatcher matcher=matchers.computeIfAbsent(probe,key->new FingerprintMatcher(templates.get(key)));
                double score=matcher.match(templates.get(candidate));
                if(!Double.isFinite(score)||score<0) throw new IllegalStateException("Invalid matcher score");
                row.addProperty("status","ok");row.addProperty("score",score);
                row.addProperty("probe_minutiae",counts.get(probe));row.addProperty("candidate_minutiae",counts.get(candidate));
            } catch(Exception ex) {row.addProperty("status","failed");row.addProperty("error",ex.toString());}
            row.addProperty("match_seconds",(System.nanoTime()-start)/1e9);pairs.add(row);
        }
        JsonObject result=new JsonObject();result.addProperty("sourceafis_version",VERSION);result.addProperty("dpi",dpi);
        result.addProperty("java_version",System.getProperty("java.version"));result.add("images",images);result.add("pairs",pairs);
        Files.writeString(Paths.get(args[1]),gson.toJson(result),StandardCharsets.UTF_8);
        System.out.println("[SourceAFIS] scores "+pairs.size());
    }
}
