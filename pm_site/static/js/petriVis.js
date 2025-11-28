document.addEventListener("DOMContentLoaded", function () {
    // Obtener datos desde el script en la plantilla
    
    const petriDataScript = document.getElementById("petri-data");
    if (!petriDataScript) {
        console.error("Error: No se encontró el elemento 'petri-data'.");
        return;
    }

    const petriData = JSON.parse(petriDataScript.textContent);
    const { places, transitions, arcs } = petriData;

    //console.log(places)
    //console.log(transitions)
    //console.log(arcs)

    function parseLabels(label) {
        if (label.includes('hid') || label.includes('skip') || label.includes('init')) {
            return '';
        }

        label = label.replace(/^\((.*)\)$/, '$1').trim();
        const commaIndex = label.indexOf(',');

        if (commaIndex !== -1) {
            return label.substring(0, commaIndex);  // El trim elimina espacios extras
        }

        return label;
    }

    let elements = [];
    const baseFontSize = 16;
    const minNodeWidth = 50;
    const nodeHeight = 50;
    const nodePadding = 24;

    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    context.font = `${baseFontSize}px sans-serif`;

    function computeNodeWidth(label) {
        const textWidth = label ? context.measureText(label).width : 0;
        return Math.max(minNodeWidth, Math.ceil(textWidth + nodePadding));
    }

    // Agregar nodos de lugares (places)
    places.forEach(place => {

        if (place.includes('source')) {
            nodeClasses = 'source-node';
        } else if (place.includes('sink')) {
            nodeClasses = 'sink-node';
        }else{
            nodeClasses = 'place';
        }

        const nodeWidth = computeNodeWidth('');

        elements.push({
            data: { id: place, label: '', width: nodeWidth, height: nodeHeight },
            classes: nodeClasses
        });
    });

    // Agregar nodos de transiciones (transitions)
    transitions.forEach(transition => {
        label = parseLabels(transition)
        if (label.length == 0){
            nodeClasses = 'transition-silent'
        } else {
            nodeClasses = 'transition-normal'
        }

        const nodeWidth = computeNodeWidth(label);
            
        elements.push({
            data: { id: transition, label: label, width: nodeWidth, height: nodeHeight },
            classes: nodeClasses
        });
    });

    // Agregar aristas (arcs)
    arcs.forEach(arc => {
        let [source, target] = arc;
        elements.push({
            data: { source: source, target: target }
        });
    });

    // Inicializar Cytoscape.js
    let cy = cytoscape({
        container: document.getElementById("cy"),
        elements: elements,
        style: [
            {
                selector: "node.place",
                style: {
                    "shape": "ellipse",
                    "background-color": "#FFFFFF",
                    "label": "data(label)",
                    "color": "#000",
                    "text-valign": "center",
                    "text-halign": "center",
                    "font-size": `${baseFontSize}px`,
                    'width': 'data(width)',
                    'height': nodeHeight,
                    'border-width' : 1,
                    'border-color' : '#000', 
                }
            },
            {
                selector: "node.sink-node, node.source-node",
                style: {
                    "shape": "ellipse",
                    "background-color": "#707070",
                    'border-width' : 1,
                    'border-color' : '#000',
                    'width': 'data(width)',
                    'height': nodeHeight, 
                }
            },
            {
                selector: "node.transition-normal",
                style: {
                    "shape": "rectangle",
                    "background-color": "#FFFFFF",
                    "label": "data(label)",
                    "color": "#000",
                    "text-valign": "center",
                    "text-halign": "center",
                    "font-size": `${baseFontSize}px`,
                    'width': 'data(width)',
                    'height': nodeHeight,
                    'border-width' : 1,
                    'border-color' : '#000', 
                }
            },
            {
                selector: "node.transition-silent",
                style: {
                    "shape": "rectangle",
                    "background-color": "#000000",
                    "label": "data(label)",
                    "color": "#000",
                    "text-valign": "center",
                    "text-halign": "center",
                    "font-size": `${baseFontSize}px`,
                    'width': 'data(width)',
                    'height': nodeHeight,
                    'border-width' : 1,
                    'border-color' : '#000', 
                }
            },
            {
                selector: "edge",
                style: {
                    "width": 2,
                    "line-color": "#2c3e50",
                    "target-arrow-shape": "triangle",
                    "target-arrow-color": "#2c3e50",
                }
            }
        ],
        layout: {
            name: 'dagre',
            rankDir: 'LR',  // Left to Right (de izquierda a derecha)
        },
        // Configuración del zoom
        minZoom: 0.1,  // Mínimo zoom
        maxZoom: 3,    // Máximo zoom
        zoomingEnabled: true,  // Permitir zoom
        userZoomingEnabled: true,  // Permitir que el usuario haga zoom
        wheelSensitivity: 0.1,
    });

    // Primero, almacenamos todas las aristas entre nodos.
    let edgeMap = new Map();

    // Contar las aristas entre pares de nodos
    cy.elements('edge').forEach(edge => {
        let sourceNode = edge.source();
        let targetNode = edge.target();

        // Crear una clave única para las aristas
        let edgeKey = `${sourceNode.id()}-${targetNode.id()}`;

        // Si ya existe una arista en esta dirección, marcaremos las dos aristas
        if (!edgeMap.has(edgeKey)) {
            edgeMap.set(edgeKey, []);
        }
        edgeMap.get(edgeKey).push(edge);
    });

    // Ahora procesamos las aristas y les damos estilo
    cy.elements('edge').forEach(edge => {
        let sourceNode = edge.source();
        let targetNode = edge.target();
        
        // Crear la clave para la arista
        let edgeKey = `${sourceNode.id()}-${targetNode.id()}`;

        // Comprobar si hay una arista en la dirección opuesta (B -> A)
        let reverseEdgeKey = `${targetNode.id()}-${sourceNode.id()}`;

        // Si hay una arista en la dirección opuesta
        if (edgeMap.has(reverseEdgeKey)) {
            // Ambas aristas (A -> B y B -> A) se deben representar como curvas
            edge.style({
                'curve-style': 'unbundled-bezier',
            });
        } else {
            // Si no hay arista en la dirección opuesta, aplicamos el estilo normal
            let sourcePos = sourceNode.position();
            let targetPos = targetNode.position();

            // Si la conexión es horizontal o vertical, la línea debe ser recta
            if (sourcePos.x === targetPos.x || sourcePos.y === targetPos.y) {
                edge.style({
                    'curve-style': 'straight',
                });
            } else {
                // Si la conexión es diagonal, la línea debe ser curva
                edge.style({
                    'curve-style': 'unbundled-bezier',
                });
            }
        }
    });

});
