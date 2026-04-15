const fs = require('fs');
const content = fs.readFileSync('/Users/hamoodi/new code 2-6/Social Media LLM/app/routes/app_pages.py', 'utf8');
const scriptRegex = /<script>([\s\S]*?)<\/script>/g;
let match;
let i = 0;
while ((match = scriptRegex.exec(content)) !== null) {
    i++;
    const js = match[1];
    try {
        new Function(js);
        console.log(`Script block ${i}: VALID`);
    } catch (e) {
        console.error(`Script block ${i}: INVALID`);
        console.error(e.message);
        // Find line number in block
        const lines = js.split('\n');
        // This is a rough estimation
        console.log("Estimated content near error:");
        console.log(js.substring(0, 500)); 
    }
}
