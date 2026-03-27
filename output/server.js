require('dotenv').config();
const express = require("express");
const cors = require("cors");
const Groq = require("groq-sdk");

const app = express();
app.use(cors({
  origin: '*' // you can restrict to your Vercel URL later
}));
app.use(express.json());

app.post("/api/analyse", async (req, res) => {
  try {
    const { prompt, apiKey } = req.body;

    if (!apiKey) {
      return res.status(400).json({ error: "No API key provided. Enter your Groq API key in the ReconAI tool settings." });
    }

    const groq = new Groq({ apiKey });

    const response = await groq.chat.completions.create({
      model: "llama-3.3-70b-versatile", // fast & free on Groq
      max_tokens: 1000,
      messages: [{ role: "user", content: prompt }]
    });

    console.log("Groq response:", JSON.stringify(response).slice(0, 200));

    // Send in same shape frontend expects
    res.json({
      content: [{ text: response.choices[0]?.message?.content || "No response" }]
    });

  } catch (err) {
    console.error("Error:", err.message);
    res.status(500).json({ error: err.message });
  }
});

app.listen(5000, () => console.log("✅ Server on http://localhost:5000"));