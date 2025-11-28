document.addEventListener('DOMContentLoaded', function () {
    //console.log('afawe')
    const optimizationField = document.querySelector('[id$="-optimization_method"]');
    if (optimizationField) {
        optimizationField.addEventListener('change', function () {
        const selectedOptimizer = this.value;
        const hyperparametersContainer = document.getElementById('dynamic-fields');
        hyperparametersContainer.innerHTML = '';  

        if (selectedOptimizer === 'NSGAII' || selectedOptimizer === 'SPEA2' || selectedOptimizer === 'PARALLEL - NSGAII' || selectedOptimizer === 'PARALLEL - SPEA2') {
            hyperparametersContainer.innerHTML += `
            <div class="mb-3">
                <label for="population_size">Tamaño de Población</label>
                <input type="number" id="population_size" name="population_size" class="form-control" value=100 required>
            </div>
            <div class="mb-3">
                <label for="offspring_population_size">Tamaño de Población de Descendencia</label>
                <input type="number" id="offspring_population_size" name="offspring_population_size" class="form-control" value=100 required>
            </div>

            <div class="mb-3">
                <h5>Mutación</h5>
                <div class="form-group">
                    <label for="mutation_type">Tipo de Mutación</label>
                    <select id="mutation_type" name="mutation_type" class="form-select">
                        <option value="polynomial">Polynomial Mutation</option>
                        <option value="random">Random Mutation</option>
                        <option value="uniform">Uniform Mutation</option>
                        <option value="non_uniform">Non Uniform Mutation</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="mutation_probability">Probabilidad de Mutación</label>
                    <input type="number" step="0.01" id="mutation_probability" name="mutation_probability" class="form-control" placeholder="Introduce la probabilidad de mutación" value=0.17 required>
                </div>
            </div>

            <div class="mb-3">
                <h5>Crossover</h5>
                <div class="form-group">
                    <label for="crossover_type">Tipo de Crossover</label>
                    <select id="crossover_type" name="crossover_type" class="form-select">
                        <option value="pmx">PMX Crossover</option>
                        <option value="sbx">SBX Crossover</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="crossover_probability">Probabilidad de Crossover</label>
                    <input type="number" step="0.01" id="crossover_probability" name="crossover_probability" class="form-control" placeholder="Introduce la probabilidad de crossover" value=0.2 required>
                </div>
            </div>

            <div class="mb-3">
                <label for="max_evaluations">Número de Evaluaciones</label>
                <input type="number" id="max_evaluations" name="max_evaluations" class="form-control" value=100 required>
            </div>

            `;
        } else if (selectedOptimizer === 'NSGAIII' || selectedOptimizer === 'PARALLEL - NSGAIII') {
            hyperparametersContainer.innerHTML += `
            <div class="mb-3">
                <label for="population_size">Tamaño de Población</label>
                <input type="number" id="population_size" name="population_size" class="form-control" value=100 required>
            </div>

            <div class="mb-3">
                <h5>Mutación</h5>
                <div class="form-group">
                    <label for="mutation_type">Tipo de Mutación</label>
                    <select id="mutation_type" name="mutation_type" class="form-select">
                        <option value="polynomial">Polynomial Mutation</option>
                        <option value="random">Random Mutation</option>
                        <option value="uniform">Uniform Mutation</option>
                        <option value="non_uniform">Non-Uniform Mutation</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="mutation_probability">Probabilidad de Mutación</label>
                    <input type="number" step="0.01" id="mutation_probability" name="mutation_probability" class="form-control" placeholder="Introduce la probabilidad de mutación" value=0.17 required>
                </div>
            </div>

            <div class="mb-3">
                <h5>Crossover</h5>
                <div class="form-group">
                    <label for="crossover_type">Tipo de Crossover</label>
                    <select id="crossover_type" name="crossover_type" class="form-select">
                        <option value="pmx">PMX Crossover</option>
                        <option value="sbx">SBX Crossover</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="crossover_probability">Probabilidad de Crossover</label>
                    <input type="number" step="0.01" id="crossover_probability" name="crossover_probability" class="form-control" placeholder="Introduce la probabilidad de crossover" value=0.2 required>
                </div>
            </div>

            <div class="mb-3">
                <label for="max_evaluations">Número de Evaluaciones</label>
                <input type="number" id="max_evaluations" name="max_evaluations" class="form-control" value=100 required>
            </div>
            `;
        }
        });
    }
});
