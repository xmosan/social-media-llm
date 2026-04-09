/**
 * Typography Adaptation Engine (JavaScript / TypeScript ready)
 * 
 * Provides rule-based image analysis and dynamic typography configuration 
 * for premium Islamic quote cards.
 * 
 * Target Environment: Browser (React / Next.js / Vue)
 */

// --- 1. CORE CONFIGURATION TOKENS ---

const TYPOGRAPHY_MODES = {
  LIGHT: {
    // Used when background is bright (e.g., Parchment, Sky)
    text_color: "#2F2419", // Deep warm brown
    support_color: "#5A4732",
    reference_color: "#8C6A2F",
    font_weight: "600",
    text_shadow: "none",
    use_blur_patch: false,
    dim_layer: "rgba(0, 0, 0, 0.15)" // Slight darkening to uniform the bright background
  },
  DARK: {
    // Used when background is dark (e.g., Space, Sacred Black)
    text_color: "#F5F1E8", // Warm off-white
    support_color: "#DDD6C8",
    reference_color: "#D4AF37", // Luminous Gold
    font_weight: "500",
    text_shadow: "0px 4px 16px rgba(0,0,0,0.65)",
    use_blur_patch: false,
    dim_layer: "none"
  },
  MID_LIGHT: {
    // Borderline bright (e.g., Dawn, Golden Hour)
    text_color: "#221A0F", 
    support_color: "#483A26",
    reference_color: "#6E521E",
    font_weight: "600",
    text_shadow: "0px 2px 8px rgba(255,255,255,0.2)",
    use_blur_patch: true,
    dim_layer: "rgba(255,255,255,0.25)"
  },
  MID_DARK: {
    // Borderline dark (e.g., Marble, Forest)
    text_color: "#F8F4EC", 
    support_color: "#E4DED2",
    reference_color: "#CDA834",
    font_weight: "400",
    text_shadow: "0px 4px 12px rgba(0,0,0,0.85)",
    use_blur_patch: true,
    dim_layer: "rgba(0,0,0,0.30)" // Stronger protective veil over busy backgrounds
  }
};

/**
 * --- 2. IMAGE ANALYZER ---
 * 
 * Takes an HTMLImageElement or a Canvas element and extracts pixel data.
 * Shrinks to a small block (e.g. 64x64) for ultra-fast processing.
 * 
 * @param {HTMLImageElement | HTMLCanvasElement} imageSource 
 * @returns {Object} Raw analysis metrics
 */
export function analyzeImage(imageSource) {
  // 1. Setup an off-screen canvas for fast sampling
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  
  // Downsample to 64x64 for milliseconds execution time
  const W = 64; 
  const H = 64;
  canvas.width = W;
  canvas.height = H;
  
  ctx.drawImage(imageSource, 0, 0, W, H);
  const imageData = ctx.getImageData(0, 0, W, H).data;
  
  let totalBrightness = 0;
  let centerBrightness = 0;
  let rTotal = 0, gTotal = 0, bTotal = 0;
  let centerPixels = 0;
  let totalPixels = W * H;

  // Luma weights
  const rW = 0.299, gW = 0.587, bW = 0.114;

  const lumas = [];
  const centerLumas = [];

  for (let i = 0; i < imageData.length; i += 4) {
    const r = imageData[i];
    const g = imageData[i + 1];
    const b = imageData[i + 2];
    
    const luma = r * rW + g * gW + b * bW;
    lumas.push(luma);
    
    totalBrightness += luma;
    rTotal += r; gTotal += g; bTotal += b;

    // Check if pixel is in the "Center Zone" (Text overlays usually sit in Y: 30% -> 70%, X: 20% -> 80%)
    const pixelIndex = i / 4;
    const x = pixelIndex % W;
    const y = Math.floor(pixelIndex / W);
    
    if (x > W * 0.2 && x < W * 0.8 && y > H * 0.3 && y < H * 0.7) {
      centerBrightness += luma;
      centerLumas.push(luma);
      centerPixels++;
    }
  }

  // Calculate Variance / Standard Deviation for complexity (busy vs minimal)
  const avgCenterBright = centerBrightness / centerPixels;
  let varianceSum = 0;
  for (let l of centerLumas) {
    varianceSum += Math.pow(l - avgCenterBright, 2);
  }
  const stdDev = Math.sqrt(varianceSum / centerPixels);
  const complexityScore = Math.min(1.0, stdDev / 60); // 0 = flat, 1.0 = extremely busy

  // Hue dominance
  const avgR = rTotal / totalPixels;
  const avgG = gTotal / totalPixels;
  const avgB = bTotal / totalPixels;
  
  const warmScore = avgR - (avgG + avgB) / 2;
  const coolScore = avgB - (avgR + avgG) / 2;
  const greenScore = avgG - (avgR + avgB) / 2;
  
  let dominantTone = "neutral";
  if (warmScore > 15) dominantTone = "warm";
  else if (coolScore > 15) dominantTone = "cool";
  else if (greenScore > 15) dominantTone = "green";

  const isLight = (totalBrightness / totalPixels) > 135;

  return {
    overall_brightness: totalBrightness / totalPixels, // 0 to 255
    center_brightness: avgCenterBright,               // 0 to 255
    complexity: complexityScore,                      // 0.0 to 1.0
    is_light: isLight,
    dominant_tone: dominantTone                       // "warm" | "cool" | "green" | "neutral"
  };
}


/**
 * --- 3. TYPOGRAPHY ADAPTATION ENGINE ---
 * 
 * Maps the raw analysis to deterministic aesthetic choices.
 * 
 * @param {Object} analysis Result from analyzeImage
 * @returns {Object} Structured UI config for React/CSS
 */
export function generateTypographyConfig(analysis) {
  const { center_brightness, complexity } = analysis;

  // 1. Determine base typography mode based on Center Brightness
  let modeKey = "DARK";
  
  if (center_brightness >= 165) {
    modeKey = "LIGHT";
  } else if (center_brightness >= 135) {
    // Borderline light - check if the image is too busy for light text
    modeKey = "MID_LIGHT";
  } else if (center_brightness >= 85) {
    // Borderline dark
    modeKey = "MID_DARK";
  } else {
    // Deep dark
    modeKey = "DARK";
  }

  // Deep clone to allow safe overrides
  const config = JSON.parse(JSON.stringify(TYPOGRAPHY_MODES[modeKey]));

  // 2. Assess Readability Risk (Complexity + Brightness Grey-Zone)
  const inGreyZone = center_brightness > 90 && center_brightness < 160;
  const isBusy = complexity > 0.35;
  const readabilityRisk = (isBusy || inGreyZone) ? "HIGH" : (complexity > 0.20 ? "MEDIUM" : "LOW");

  // 3. Dynamic Protection Layer (Gradient Overlay / Blur)
  // We NEVER use ugly square boxes. We use "Vignette" and Radial patches.
  if (readabilityRisk !== "LOW") {
    config.use_blur_patch = true;
    
    // Scale the dim radial gradient based on risk
    const alphaDark = readabilityRisk === "HIGH" ? "0.65" : "0.40";
    const alphaLight = readabilityRisk === "HIGH" ? "0.45" : "0.20";
    
    if (modeKey === "LIGHT" || modeKey === "MID_LIGHT") {
      // Light backgrounds need a subtle darkening veil to make dark brown pop safely
      config.overlay = `radial-gradient(ellipse at center, rgba(0,0,0,${alphaLight}) 0%, rgba(0,0,0,0) 65%)`;
    } else {
      // Dark backgrounds get a heavier, darker veil so white text cuts cleanly
      config.overlay = `radial-gradient(ellipse at center, rgba(0,0,0,${alphaDark}) 0%, rgba(0,0,0,0) 70%)`;
    }
  } else {
    config.overlay = "none";
  }

  // 4. Glow / Anamorphic Bloom Logic (Premium touch)
  if (modeKey === "DARK") {
    // Deep space/black gets a luminous gold glow behind the text
    config.glow = "radial-gradient(circle at center, rgba(212,175,55,0.15) 0%, rgba(212,175,55,0) 50%)";
  } else {
    config.glow = "none";
  }

  return {
    // Main UI Output
    text_color: config.text_color,
    support_color: config.support_color,
    reference_color: config.reference_color,
    
    font_weight: config.font_weight,
    text_shadow: config.text_shadow,
    
    overlay: config.overlay,           // Place behind text container (z-index: 1)
    glow: config.glow,                 // Place right behind text (z-index: 2)
    use_blur_patch: config.use_blur_patch, // True? Apply backdrop-filter: blur(8px) on overlay
    
    // Debug info
    _debug: {
      mode: modeKey,
      risk: readabilityRisk,
      complexity: (complexity * 100).toFixed(1) + "%",
      center_luma: center_brightness.toFixed(1)
    }
  };
}
