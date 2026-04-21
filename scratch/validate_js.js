const fs = require('fs');
const content = fs.readFileSync('app/routes/ui_assets.py', 'utf8');

// Extract STUDIO_SCRIPTS_JS
const match = content.match(/STUDIO_SCRIPTS_JS = """\n<script>\n([\s\S]*?)\n<\/script>\n"""/);
if (match) {
    const js = match[1];
    try {
        new Function(js);
        console.log("JS is valid");
    } catch (e) {
        console.error("JS Syntax Error:", e.message);
        // Find line number
        const lines = js.split('\n');
        // This won't give exact line but helps
    }
} else {
    console.log("Could not find STUDIO_SCRIPTS_JS");
}
