# The 25 hardest judge questions

Short, honest answers. Where a number is needed, read it from docs/EVALUATION.md on the day.

1. **Why not YOLO like everyone else?** A box says "this onion is bad". The norms say "up to 30% of the surface may be blackened". We need the share of the surface, so we measure defect areas per bulb. Ultralytics YOLO is also AGPL, which we keep out of a government app.

2. **What is URS?** Press coverage calls it a "relaxed-specification" category of smaller, slightly blemished onions. We could not find the official expansion or its limits, so the app defines it as "misses Grade A but within the relaxed limits" and prints that definition on every receipt. It is question 1 in our open-questions list.

3. **What if the norms change again?** A rule pack is a JSON file with a version and a hash. A new norm is a new pack; no app update to the grading code. Old receipts still verify against the pack they were issued under.

4. **What if the officer is corrupt?** The officer cannot choose which sacks are sampled (both parties' codes decide), cannot edit a signed receipt without detection, and every override is signed with a reason next to the AI's original verdict. The fleet view flags officers who override unusually often. What we cannot stop: photographing a different tray. That is why the sample draw and the photos are in the receipt.

5. **What about connectivity?** Nothing needs the network. Capture, grading, signing, the QR and verification all run offline. The log can be exported and published whenever a connection exists.

6. **Is it tamper-proof?** No. It is tamper-evident: any change to a signed receipt breaks the signature or the re-grade. It does not prove the photographed onions are the ones sold.

7. **How accurate is it?** On held-out real photos from a public dataset, see the table in docs/EVALUATION.md. Against trained graders and calipers we do not know yet; those studies are designed and need one week of field work.

8. **Why should anyone trust your numbers?** Every number in our docs is written by a script into reports/ and rendered from there. None comes from synthetic images.

9. **Isn't a colour threshold model primitive?** It is transparent: every threshold is in one file whose hash is printed on the receipt, and it runs on any phone. We add a learned model only where it beats the colour model on held-out real photos, and we say where it does not.

10. **Can you see rot inside the onion?** No. We measure the visible surface, and we look twice after shaking the tray. Internal rot needs other sensors; that is future work, not a claim.

11. **How do you get millimetres from a photo?** A printed marker mat, a plain A4 sheet, a coin, or (worst) the camera's own geometry. The tier used is printed on the receipt and widens the size uncertainty. We also correct for the bulb's equator sitting above the table.

12. **What happens at a size limit?** If a bulb's size interval crosses a limit, the app does not guess: it sends that bulb to "needs human check".

13. **Why is the verdict by weight?** Procurement is settled by weight. We estimate each bulb's weight from its size (a fitted curve once the kitchen-scale data is in) and report shares by weight and by count.

14. **How many onions do you need to sample?** The sequential test decides after each tray: accept, reject, sample more (with a tray count), or hand over to an inspector.

15. **Licensing?** Our code is MIT. Runtime dependencies are MIT, Apache-2.0, BSD, ISC or OFL. No AGPL. Demo photos are CC-BY 4.0 with attribution.

16. **Cost per centre?** A phone the officer already has and a printed A4 mat. No server is required. With a sync server, one small instance can serve many centres, but we have not costed it.

17. **Scalability to 500 centres?** Grading scales with phones, not servers. The part that needs central work is publishing logs and the fleet view, which is a static file per centre per day in the simplest form.

18. **Privacy and the DPDP Act?** The farmer reference stays on the phone and on the receipt the farmer receives. Location is rounded to about a kilometre and only with permission. Nothing is uploaded by default. A centre can use a reference number instead of a name.

19. **What if the farmer disagrees?** They contest any bulb in the app. The bulb goes to "needs human check" until an officer decides, and both steps stay on the signed record.

20. **What if the phone's key is stolen?** An unlocked stolen phone can sign receipts; the key fingerprint on every receipt lets a centre revoke that device and flag its receipts. Keys cannot be copied out of the app.

21. **What if the photo is taken in bad light?** The Capture Guard refuses it and tells the officer why. It does not grade what it cannot see.

22. **Does it work on white onions?** Worse than on red ones, especially on a white sheet. Use the dark side of the mat or a dark cloth. It is in our limitations.

23. **Why should a centre adopt this rather than trained graders?** It does not replace graders. It gives the same answer for the same onions in every centre, shows its reasons, and leaves a record both sides can check. Our human-baseline study measures how much graders disagree today.

24. **What did the earlier prototype get wrong?** Its model and metrics came from synthetic images, its intervals treated bulbs in one tray as independent, and its verify page trusted the server. We kept the good ideas and rebuilt the rest (AUDIT.md).

25. **What would you do with one more month?** Field photos from two centres, the three studies, retrain the learned model on them, calibrate the uncertainty against hand-sorted lots, and get the official circular so every pack becomes "verified".
