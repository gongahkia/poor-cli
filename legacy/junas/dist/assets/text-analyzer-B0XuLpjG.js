import{n as f}from"./three-SXxGkC3e.js";function g(t){const n=t.length,o=t.replace(/\s/g,"").length,s=t.split(/\s+/).filter(i=>i.length>0).length,a=t.split(/[.!?]+/).filter(i=>i.trim().length>0).length,e=t.split(/\n\s*\n/).filter(i=>i.trim().length>0).length,r=s>0?o/s:0,c=a>0?s/a:0,u=Math.ceil(s/200),d=Math.ceil(s/150);return{characters:n,charactersNoSpaces:o,words:s,sentences:a,paragraphs:e,averageWordLength:Math.round(r*10)/10,averageSentenceLength:Math.round(c*10)/10,readingTimeMinutes:u,speakingTimeMinutes:d}}function m(t){const n=g(t),o=y(t),s=Math.round(206.835-1.015*(n.words/Math.max(n.sentences,1))-84.6*(o/Math.max(n.words,1))),a=Math.round((.39*(n.words/Math.max(n.sentences,1))+11.8*(o/Math.max(n.words,1))-15.59)*10)/10;let e;return s>=90?e="Very Easy - 5th grade level":s>=80?e="Easy - 6th grade level":s>=70?e="Fairly Easy - 7th grade level":s>=60?e="Standard - 8th-9th grade level":s>=50?e="Fairly Difficult - 10th-12th grade level":s>=30?e="Difficult - College level":e="Very Difficult - Professional/Legal level",{fleschReadingEase:Math.max(0,Math.min(100,s)),fleschKincaidGrade:Math.max(0,a),interpretation:e}}function y(t){const n=t.toLowerCase().split(/\s+/);let o=0;for(const s of n)o+=p(s);return o}function p(t){if(t=t.replace(/[^a-z]/g,""),t.length<=3)return 1;t=t.replace(/(?:[^laeiouy]es|ed|[^laeiouy]e)$/,""),t=t.replace(/^y/,"");const n=t.match(/[aeiouy]{1,2}/g);return n?n.length:1}function w(t,n=10){const o=f(t),s=o.nouns().out("array"),a=o.terms().out("array"),e=new Set(["the","a","an","and","or","but","in","on","at","to","for","of","with","by","from","as","is","was","are","were","been","be","have","has","had","do","does","did","will","would","could","should","may","might","must","shall","this","that","these","those","it","its","they","them","their","we","us","our","you","your","he","him","his","she","her","i","me","my","not","no","yes","if","then","else","when","where","which","who","whom","what","how","why","all","each","every","both","few","more","most","other","some","such","only","own","same","so","than","too","very","just","also","now","here","there","any","many","much"]),r=new Map,c=[...s,...a];for(const i of c){const l=i.toLowerCase().trim();l.length>2&&!e.has(l)&&r.set(l,(r.get(l)||0)+1)}const u=c.length;return Array.from(r.entries()).sort((i,l)=>l[1]-i[1]).slice(0,n).map(([i,l])=>({word:i,count:l,frequency:Math.round(l/u*1e4)/100}))}function S(t){const n=t.split(`
`),o=/^\s*\d+\.(\d+\.?)*\s+/,s=n.some(h=>o.test(h)),a=/^\s*\([a-z]\)|\([ivx]+\)/i,e=n.some(h=>a.test(h)),r=/^\s*[-•*]\s+/,c=n.some(h=>r.test(h)),d=/"[^"]+"\s+(means|refers to|shall mean)/i.test(t),i=/^([A-Z][A-Z\s]+[A-Z]|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*$/,l=n.filter(h=>i.test(h.trim())&&h.trim().length>3).map(h=>h.trim()).slice(0,20);return{hasNumberedSections:s,hasLetterSections:e,hasBulletPoints:c,hasDefinitions:d,detectedSections:l}}function M(t){const n=g(t),o=m(t),s=w(t,10),a=S(t);let e=`## Document Analysis Results

`;if(e+=`### Text Statistics
`,e+=`| Metric | Value |
`,e+=`|--------|-------|
`,e+=`| Words | ${n.words.toLocaleString()} |
`,e+=`| Sentences | ${n.sentences.toLocaleString()} |
`,e+=`| Paragraphs | ${n.paragraphs.toLocaleString()} |
`,e+=`| Characters | ${n.characters.toLocaleString()} |
`,e+=`| Avg. Word Length | ${n.averageWordLength} chars |
`,e+=`| Avg. Sentence Length | ${n.averageSentenceLength} words |
`,e+=`| Reading Time | ~${n.readingTimeMinutes} min |
`,e+=`| Speaking Time | ~${n.speakingTimeMinutes} min |

`,e+=`### Readability
`,e+=`- **Flesch Reading Ease:** ${o.fleschReadingEase}/100
`,e+=`- **Flesch-Kincaid Grade:** ${o.fleschKincaidGrade}
`,e+=`- **Interpretation:** ${o.interpretation}

`,s.length>0){e+=`### Key Terms
`,e+=`| Term | Occurrences |
`,e+=`|------|-------------|
`;for(const c of s)e+=`| ${c.word} | ${c.count} |
`;e+=`
`}e+=`### Document Structure
`;const r=[];if(a.hasNumberedSections&&r.push("Numbered sections"),a.hasLetterSections&&r.push("Letter/Roman sections"),a.hasBulletPoints&&r.push("Bullet points"),a.hasDefinitions&&r.push("Definitions section"),r.length>0?e+=`**Detected features:** ${r.join(", ")}

`:e+=`No structured formatting detected.

`,a.detectedSections.length>0){e+=`**Section headings found:**
`;for(const c of a.detectedSections.slice(0,10))e+=`- ${c}
`;e+=`
`}return e+=`---
*Analyzed using local NLP processing (no AI service required)*`,e}export{S as analyzeDocumentStructure,w as extractKeywords,M as formatTextAnalysis,m as getReadabilityScores,g as getTextStatistics};
