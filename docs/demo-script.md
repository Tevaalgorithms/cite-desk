# CiteDesk — Demo script

About 25 minutes: why it exists, which RAG was chosen and why, a live demo of the admin side and then the question side, and a deep dive. "**Do**" is what you click or type, and "**Say**" is what you tell the audience. Every question below has a known answer in the sample documents. Model answers can vary slightly, so do one full run-through on the day.

## 0. Before you start (about 10 minutes, once)

Use a separate database and a separate Pinecone namespace, so the demo never touches your real data and can be repeated.

```bash
export CITEDESK_DATABASE_URL=sqlite:///demo.db
export CITEDESK_ENVIRONMENT=demo          # a separate Pinecone namespace, so dev data is untouched

uv run --extra models citedesk add data/sample/acme-handbook.md \
  --title "Acme Robotics Employee Handbook" --license "CC0 (synthetic sample)" --publish
uv run --extra models citedesk add data/sample/acme-facilities-guide.md \
  --title "Acme Robotics Office and Facilities Guide" --license "CC0 (synthetic sample)"   # a draft, not published

uv run --extra models citedesk serve --port 8010                      # same terminal, so it uses the demo database
# in another terminal: cd apps/web && NEXT_PUBLIC_API_URL=http://localhost:8010 npm start
```

- **Two browser windows:** a normal one signed in as **admin** and a private one signed in as **analyst**. Get a token with `uv run citedesk token --user alice --role admin | pbcopy` (and `--user bob --role analyst`).
- **The "policy changed" file:** `sed 's/20 days/25 days/' data/sample/acme-handbook.md > ~/Desktop/acme-handbook-v2.md`
- **The "no license" file:** `data/sample/acme-it-support-guide.md`. Copy it to the Desktop so it is easy to pick.
- **Open in tabs:** the README's Architecture diagram and its two "journey" sections.
- Do not demo a live web-page import: it is tested against a simulated site but has not been tried on a real one.

To repeat the demo, delete `demo.db` and run the three commands again. The Pinecone `demo` namespace repairs itself from the database when the API starts.

## 1. Why this exists (2 minutes)

**Say:** "Employees ask HR the same questions all day: how many vacation days do I get, when must I return my laptop. A general chatbot can't answer these properly, for three reasons:

1. **It doesn't know our policy**, which is our own text and changes every year.
2. **It makes things up confidently**, and in HR a wrong answer is a real problem.
3. **It gives no proof.** You can't tell where an answer came from.

CiteDesk answers only from the company's own published documents, shows the exact source of every sentence, and **says 'I can't find that' instead of guessing.**"

## 2. What was built (1 minute)

**Do:** show the README Architecture diagram.

**Say:** "Two sides that never call each other. The **admin side** turns documents into small searchable pieces. The **answer side** finds the right pieces and writes a checked answer. They meet only in a database and a search index, so each can change without breaking the other, and a test enforces that rule."

## 3. Which RAG, and why (3 minutes)

**Say:** "I use **hybrid RAG with a reranker and a citation checker**: keyword search plus meaning search, then a closer second look, then a check on every sentence."

| Option | Decision | Reason |
| --- | --- | --- |
| Vector search only | No | Misses exact terms such as codes and policy names |
| **Hybrid (keyword + vector) with a reranker** | **Yes** | Keywords catch exact terms, vectors catch meaning, the reranker picks the best |
| Agentic RAG (the AI plans and searches several times) | **Measured, not built** | On 12 multi-part questions, plain retrieval already gave the writer every needed section 12 of 12 times, so an agent adds cost and delay for no gain (ADR-018) |
| Graph RAG | Not applicable | Handbooks are sections of text, not networks of related entities |
| Fine-tuning a model | No | It cannot cite sources and goes stale when policy changes |
| Put the whole handbook in the prompt | No | Works for a small file but does not scale, costs more per question and gives no guarantee of citations |

**Say:** "I add complexity only where measurement shows a need."

## 4. Demo part A: the admin side (6 minutes)

**Do:** admin window, **Admin** page.

1. **The table.** "Two documents. The handbook is **published**. The facilities guide is a **draft**: saved, but invisible to questions."
2. **Prove it is invisible.** In the analyst window ask **"What is the dress code?"** and it is refused. "It is in the facilities guide, but that is still a draft."
3. **Preview.** Click **Preview** on the facilities guide. "Nine chunks, each with its section path, like `Office access > Badges`. This is exactly what will be searched and cited."
4. **Publish.** Click **Publish**. In the analyst window ask **"What is the dress code?"** again and it answers **smart casual**, citing `Dress code > What to wear`.
5. **The license rule, live.** Upload `acme-it-support-guide.md` in the **Add a document** form with the **License** box left empty and any source (for example "demo upload"). It appears as a draft. Click **Publish** and it is refused: *"Record the document's license before publishing."* "Every document needs a recorded license before it can go live. That is a deliberate rule."
6. **Fix it inline.** Click **Add license**, type "CC0 (synthetic sample)", save, then **Publish**. It works.
7. **Duplicate protection.** Upload the same file again and it is refused, naming the existing document.
8. **Audit log.** Scroll down: who added, licensed and published what, and when.

**Say:** "Nothing reaches users until a person has reviewed it and recorded the license, and every step is logged."

## 5. Demo part B: the question side (7 minutes)

**Do:** analyst window.

1. **The status bar.** "The top bar shows which model answers: **Live · openai · gpt-5.4-nano**." Click **Check connection**. "I chose the cheapest model that scored well in my measurements. A question costs about a hundredth of a cent."
2. **A plain question:** *How many vacation days do I get?* gives **20 days** with a citation chip. Click the chip: "the source drawer opens the exact passage with the sentence highlighted."
3. **A paraphrase:** *How much time off do I get when I have a baby?* gives **16 weeks of paid parental leave**, and with the OpenAI model usually adds that it can start up to 2 weeks before the birth (the built-in writer gives only the 16 weeks). "The question never says 'parental leave'. Meaning search found it."
4. **A multi-part question:** *How many vacation days and how many sick days do I get?* gives both answers with **two citations**.
5. **From the document you just published:** *When is the IT helpdesk open?* gives **8:00 to 18:00 on weekdays**.
6. **It refuses:** *What is the capital of France?* and *Does the company offer stock options?* are answered with "I couldn't find that in the handbook". "No guess, and for the first one no model call at all."
7. **A trap:** *What is the guest wifi password?* gives that the password is **shown on the screen at the front desk and changes every week**. "It did not invent a password."
8. **Freshness (the finale):** ask the vacation question and get 20 days. In the admin window click **Replace** on the handbook, choose `acme-handbook-v2.md` and click **Replace now**. Ask again and get **25 days**. "The old version is retired and the new one live, in one step. Old answers are never served after a change."

## 6. Deep dive (10 minutes)

**The path of a question.** Walk the 14 steps of "The journey of one question" in the README:

- **Keyword search (BM25)** finds exact words. **Vector search** finds meaning, using the local `bge-small` model (384 numbers per text), stored in the Pinecone index `cite-desk`.
- **Reciprocal Rank Fusion** merges the two lists by position: first in both lists scores 1/61 + 1/61 = 0.0328.
- **A cross-encoder** reads the question and each passage together and rescores them. Below −10 means "nothing relevant", so no model is called.
- **The writer** (`gpt-5.4-nano`) may only use the numbered passages. **The verifier**, which is plain code, checks every sentence for a citation, matching numbers and quotes, and word support. It retries once, then refuses.

**The path of a document.** Walk "The journey of one document": parse into sections, chunk, draft, license, embed, publish in one transaction, and replace.

**Quality, with real numbers.** On the sample question sets, `gpt-5.4-nano` answered 34 of 37 answerable questions correctly and refused 14 of 14 unanswerable ones. The no-model quoting writer also got 34 of 37 but wrongly answered 3 of the 14 unanswerable ones. Quality gates run in CI on every pull request, with 7 CI jobs and over 230 Python tests.

**Engineering choices:**

- The database is the source of truth and Pinecone is a rebuildable copy.
- Keys are never in git: `.env` locally and encrypted AWS SSM Parameter Store for production.
- Admin-only routes, rate limits, and protection against server-side request forgery on web-page import.

**Honest limits (say these yourself before anyone asks):**

1. **The verifier checks support, not meaning.** In a test it passed "do **not** receive 20 days". Closing this gap is the next fix.
2. **The test questions are few and written by us**, so the numbers show the pipeline works, not that it will be accurate on a real handbook.
3. **Sign-in uses development tokens**, not company sign-in (OIDC).
4. English only, no streaming, no saved conversations, no PDF or Word files.
5. **It is not deployed yet.** It runs locally, and Lightsail is the plan.

## 7. Likely questions

| Question | Answer |
| --- | --- |
| Why not LangChain? | Same algorithms, but they are written directly so every piece is small, swappable and testable. LangGraph is used for the step flow only. |
| What if OpenAI is down? | The question is refused as "model unavailable", and that failure is not cached. |
| Can a document inject instructions? | The prompt tells the model to ignore instructions inside passages and the verifier checks the output. A planted-injection test is not built yet. |
| Why local embedding models? | Free, private, no per-question cost, and swappable in one file. |
| How do you know a change did not make it worse? | Retrieval and answer metrics are compared with stored baselines in CI, and a pull request fails if they drop. |
| What breaks at scale? | The keyword index and the answer cache live in one process: fine for thousands of passages, not millions. |

## 8. Closing (30 seconds)

"An assistant that answers only from approved documents, proves every sentence, refuses when unsure, and stays current when policy changes. Every design choice was measured, and I have told you where it is weak."
