function amountValue(input) {
    const value = Number.parseFloat(input?.value || "0");
    return Number.isFinite(value) ? value : 0;
}

function currency(value) {
    return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
    }).format(value);
}

function updatePaycheckPreview(form) {
    const gross = amountValue(
        form.querySelector('[data-paycheck-amount="gross"]')
    );
    const actual = amountValue(
        form.querySelector('[data-paycheck-amount="actual"]')
    );
    const standardDeductions = Array.from(
        form.querySelectorAll("[data-paycheck-deduction]")
    ).reduce((total, input) => total + amountValue(input), 0);
    const customDeductions = Array.from(
        form.querySelectorAll("[data-custom-deduction]")
    ).reduce((total, input) => total + amountValue(input), 0);
    const expected = gross - standardDeductions - customDeductions;
    const discrepancy = actual - expected;
    const expectedOutput = form.querySelector("[data-expected-net]");
    const discrepancyOutput = form.querySelector("[data-discrepancy]");

    expectedOutput.textContent = currency(expected);
    discrepancyOutput.textContent = `Discrepancy: ${currency(discrepancy)}`;
    discrepancyOutput.classList.toggle("warning-value", discrepancy !== 0);
}

function addDeductionRow(form) {
    const container = form.querySelector("[data-deduction-fields]");
    const row = document.createElement("div");
    row.className = "deduction-row";
    row.innerHTML = `
        <div>
            <label>Deduction name</label>
            <input name="deduction_name" maxlength="100">
        </div>
        <div>
            <label>Amount ($)</label>
            <input
                name="deduction_amount"
                type="number"
                min="0.01"
                max="1000000"
                step="0.01"
                data-custom-deduction
            >
        </div>
    `;
    container.append(row);
    row.querySelector("input").focus();
}

document.querySelectorAll(".paycheck-form").forEach((form) => {
    form.addEventListener("input", () => updatePaycheckPreview(form));
    form.querySelector("[data-add-deduction]").addEventListener(
        "click",
        () => addDeductionRow(form)
    );
    updatePaycheckPreview(form);
});
