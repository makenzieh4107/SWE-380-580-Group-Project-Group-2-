## Threats to Validity

* **Dataset limitations:** The GitSkills sample may not represent all available skills or repositories.

* **Reuse identification:** Matching `file_sha` values show identical content but do not prove who copied whom.

* **Incomplete timestamps:** Some artifacts may not have timestamps, making chronological comparisons difficult.

* **Detection errors:** Security detection rules may produce false positives or false negatives.

* **Scanner coverage:** The scanner may not detect every security issue, especially in supporting files or scripts that are not included in the scan.

* **Interpretation:** Finding a new security capability does not prove that it is harmful, unnecessary, or malicious.

* **Comparison limitations:** Some artifacts may contain identical content or appear in multiple baseline-variant pairs. This could affect counts if repeated content is not handled consistently.

* **Validation:** A sample of detected results should be manually reviewed to check the accuracy of the analysis.

* **Data safety:** Dataset code is analyzed as data and is never executed.
