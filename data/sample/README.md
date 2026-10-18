# Sample data

`acme-handbook.md` is **synthetic demo text** written for CiteDesk. Acme Robotics is a fictional company. It is released under CC0 (public domain), so it can be copied, ingested and quoted freely. Use it for local runs, tests and CI. It is not a stand-in for a real handbook when judging answer quality.

`acme-facilities-guide.md` is a second made-up document (offices, parking, cafeteria, Wi-Fi) for trying the admin upload: add it, give it a license, publish it, then ask "How much is a parking permit?". It is not used by the evaluation sets.

`acme-it-support-guide.md` is a third made-up document (helpdesk hours, tickets, password reset, software requests, broken devices). It is meant for the live demo of the license rule: upload it **without** a license, try to publish it and see it refused, add the license in the table, then publish it and ask "When is the IT helpdesk open?". It is not used by the evaluation sets.

Example questions with known answers (and some that must be refused) are in [`evals/sample/questions.json`](../../evals/sample/questions.json).
