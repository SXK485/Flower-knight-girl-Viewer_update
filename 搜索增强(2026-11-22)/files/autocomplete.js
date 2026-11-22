var autocomplete = {
	character: new Set(),
	artist: new Set(),
	cv: new Set(),
	female: new Set(),
	male: new Set(),
	misc: new Set(),
	location: new Set(),
}

function autoCompleteName(input, values){
    let currentFocus;
    input.addEventListener("input", function(e){
        let inputValue = this.value.split(",")[this.value.split(",").length-1].trim();
        if(inputValue.startsWith("!") || inputValue.startsWith("-")){
            inputValue = inputValue.substr(1);
        }

        closeAllLists();
        if(!values){
            return false;
        }
        currentFocus = 0;

        let valueContainer = document.createElement("div");
        valueContainer.setAttribute("id", this.id + "autocomplete");
        valueContainer.setAttribute("class", "autocomplete-values");
        this.parentNode.appendChild(valueContainer);

        for(let value of values){
            let autoElem;
            if(value.eng.substr(0, inputValue.length).toUpperCase() == inputValue.toUpperCase()){
                autoElem = createAutoElem(value.eng, inputValue);
                autoElem.setAttribute("autocomplete", value.eng)
            } else if(value.jap.substr(0, inputValue.length).toUpperCase() == inputValue.toUpperCase()){
                autoElem = createAutoElem(value.jap, inputValue);
                autoElem.setAttribute("autocomplete", value.jap)
            } else {
                let foundEng = false;
                for(let alias of value.engAlias){
                    if(alias.substr(0, inputValue.length).toUpperCase() == inputValue.toUpperCase()){
                        foundEng = true;
                        autoElem = createAutoElem(value.eng, inputValue, alias);
                        // if(value.eng.includes(alias)){
                        // 	autoElem.setAttribute("autocomplete", value.eng);
                        // } else {
                        // 	autoElem.setAttribute("autocomplete", alias);
                        // }
                        autoElem.setAttribute("autocomplete", value.eng);
                        break;
                    }
                }
                if(!foundEng){
                    for(let alias of value.japAlias){
                        if(alias.substr(0, inputValue.length).toUpperCase() == inputValue.toUpperCase()){
                            autoElem = createAutoElem(value.jap, inputValue, alias);
                            let autoValue = value.jap;
                            if(window.CN_SERIES_ALIASES && window.CN_SERIES_ALIASES.has(alias)){
                                autoValue = alias;
                            }
                            autoElem.setAttribute("autocomplete", autoValue);
                            break;
                        }
                    }
                }
            }

            if(autoElem != null){
                valueContainer.appendChild(autoElem);
            }
        }

        if(valueContainer.children.length > 0){
        	this.parentNode.appendChild(valueContainer);
        	addActive(valueContainer.getElementsByTagName("div"));
        }

        valueContainer.addEventListener("click", function(e){
            let idx = input.value.lastIndexOf(",") + 1;
            let final = input.value.substr(0, idx) + " ";
            let typed = input.value.substr(idx).trim();
            if(typed.startsWith("!")){
                final += "!";
            } else if(typed.startsWith("-")){
                final += "-";
            }
            final += e.target.closest(".autocomplete-value").getAttribute("autocomplete");
            closeAllLists();
            final = final.trim();
            input.value = final;
        });
    });

    input.addEventListener("keydown", function(e){
        let valueContainer = document.getElementById(this.id + "autocomplete");
        if (valueContainer) valueContainer = valueContainer.getElementsByTagName("div");
        switch(e.code){
            case "ArrowDown":
                currentFocus++;
                addActive(valueContainer);
                scrollTo(false, valueContainer[currentFocus]);
            break;
            case "ArrowUp":
                currentFocus--;
                addActive(valueContainer);
                scrollTo(true, valueContainer[currentFocus]);
            break;
            case "Enter":
            case "ArrowRight":
                e.preventDefault();
                if (valueContainer) valueContainer[currentFocus].click();
            break;
            case "Tab":
                if(this.value != ""){
                    e.preventDefault();
                    if (valueContainer) valueContainer[currentFocus].click();
                } else {
                    closeAllLists();
                }
            break;
        }
    });

    function scrollTo(top, elem){
    	let mainElem = document.getElementsByClassName("autocomplete-values")[0];
    	let scrollPos = mainElem.scrollTop;
    	let elemLoc = elem.offsetTop;
    	let mainHeight = mainElem.offsetHeight;
    	let elemHeight = elem.offsetHeight;
    	if(top){
    		if(elemLoc < scrollPos){
    			elem.scrollIntoView(top);
    		}
    	} else {
    		if(scrollPos + mainHeight < elemLoc + elemHeight){
    			elem.scrollIntoView(top);
    		}
    	}
    }

    function createAutoElem(trueName, found, fullAlias=""){
        let autoElem = document.createElement("div");
        autoElem.classList = "autocomplete-value"
        trueNameC = trueName.toUpperCase();
        foundC = found.toUpperCase();
        if(trueNameC.indexOf(foundC) == -1){
            autoElem.innerHTML = trueName + "<span class='autocomplete-alias'>Alias: <strong>" + fullAlias.substr(0, found.length) + "</strong>" + fullAlias.substr(found.length) + "</span>";
        } else if(trueNameC.indexOf(foundC) != 0){
            autoElem.innerHTML = trueName.substr(0, trueNameC.indexOf(foundC)) + "<strong>" + trueName.substr(trueNameC.indexOf(foundC), found.length) + "</strong>" + trueName.substr(trueNameC.indexOf(foundC) + found.length)
        } else {
            autoElem.innerHTML = "<strong>" + trueName.substr(0, found.length) + "</strong>" + trueName.substr(found.length);
        }
        autoElem.innerHTML += "<input type='hidden' value='" + trueName + "'>";
        return autoElem;
    }

    function addActive(x){
        if (!x) return false;
        removeActive(x);
        if (currentFocus >= x.length){
        	currentFocus = 0;
        	x[currentFocus].scrollIntoView(true);
        } else if (currentFocus < 0){
        	currentFocus = (x.length - 1);
        	x[currentFocus].scrollIntoView(false);
        }
        x[currentFocus].classList.add("autocomplete-active");
    }

    function removeActive(x){
        for(elem of x){
            elem.classList.remove("autocomplete-active");
        }
    }

    function closeAllLists(){
        let lists = document.getElementsByClassName("autocomplete-values");
        for(list of lists){
            list.parentNode.removeChild(list);
        }
    }
    document.addEventListener("click",closeAllLists,false);
}

function autoCompleteTag(input, values){
    let currentFocus;
    input.addEventListener("input", function(e){
        let inputValue = this.value.split(",")[this.value.split(",").length-1].trim();
        if(inputValue.startsWith("!") || inputValue.startsWith("-")){
            inputValue = inputValue.substr(1);
        }

        closeAllLists();
        if(!values){
            return false;
        }
        currentFocus = 0;

        let valueContainer = document.createElement("div");
        valueContainer.setAttribute("id", this.id + "autocomplete");
        valueContainer.setAttribute("class", "autocomplete-values");

        for(let value of values){
            let autoElem;
            if(value.name.substr(0, inputValue.length).toUpperCase() == inputValue.toUpperCase()){
                autoElem = createAutoElem(value.name, inputValue);
                autoElem.setAttribute("autocomplete", value.name)
            } else {
                for(let alias of value.aliases){
                    if(alias.substr(0, inputValue.length).toUpperCase() == inputValue.toUpperCase()){
                        autoElem = createAutoElem(value.name, inputValue, alias);
                        // if(value.name.includes(alias)){
                        // 	autoElem.setAttribute("autocomplete", value.name);
                        // } else {
                        // 	autoElem.setAttribute("autocomplete", alias);
                        // }
                        autoElem.setAttribute("autocomplete", value.name);
                        break;
                    }
                }
            }

            if(autoElem != null){
                valueContainer.appendChild(autoElem);
            }
        }

        if(valueContainer.children.length > 0){
        	this.parentNode.appendChild(valueContainer);
        	addActive(valueContainer.getElementsByTagName("div"));
        }

        valueContainer.addEventListener("click", function(e){
            let idx = input.value.lastIndexOf(",") + 1;
            let final = input.value.substr(0, idx) + " ";
            let typed = input.value.substr(idx).trim();
            if(typed.startsWith("!")){
                final += "!";
            } else if(typed.startsWith("-")){
                final += "-";
            }
            final += e.target.closest(".autocomplete-value").getAttribute("autocomplete");
            closeAllLists();
            final = final.trim();
            input.value = final;
        });
    });

    input.addEventListener("keydown", function(e){
        let valueContainer = document.getElementById(this.id + "autocomplete");
        if (valueContainer) valueContainer = valueContainer.getElementsByTagName("div");
        switch(e.code){
            case "ArrowDown":
                currentFocus++;
                addActive(valueContainer);
                scrollTo(false, valueContainer[currentFocus]);
            break;
            case "ArrowUp":
                currentFocus--;
                addActive(valueContainer);
                scrollTo(true, valueContainer[currentFocus]);
            break;
            case "Enter":
            case "ArrowRight":
            case "Tab":
                e.preventDefault();
                if (valueContainer) valueContainer[currentFocus].click();
            break;
        }
    });

    function scrollTo(top, elem){
    	let mainElem = document.getElementsByClassName("autocomplete-values")[0];
    	let scrollPos = mainElem.scrollTop;
    	let elemLoc = elem.offsetTop;
    	let mainHeight = mainElem.offsetHeight;
    	let elemHeight = elem.offsetHeight;
    	if(top){
    		if(elemLoc < scrollPos){
    			elem.scrollIntoView(top);
    		}
    	} else {
    		if(scrollPos + mainHeight < elemLoc + elemHeight){
    			elem.scrollIntoView(top);
    		}
    	}
    }

    function createAutoElem(trueName, found, fullAlias=""){
        let autoElem = document.createElement("div");
        autoElem.classList = "autocomplete-value"
        trueNameC = trueName.toUpperCase();
        foundC = found.toUpperCase();
        if(trueNameC.indexOf(foundC) == -1){
            autoElem.innerHTML = trueName + "<span class='autocomplete-alias'>Alias: <strong>" + fullAlias.substr(0, found.length) + "</strong>" + fullAlias.substr(found.length) + "</span>";
        } else if(trueNameC.indexOf(foundC) != 0){
            autoElem.innerHTML = trueName.substr(0, trueNameC.indexOf(foundC)) + "<strong>" + trueName.substr(trueNameC.indexOf(foundC), found.length) + "</strong>" + trueName.substr(trueNameC.indexOf(foundC) + found.length)
        } else {
            autoElem.innerHTML = "<strong>" + trueName.substr(0, found.length) + "</strong>" + trueName.substr(found.length);
        }
        autoElem.innerHTML += "<input type='hidden' value='" + trueName + "'>";
        return autoElem;
    }

    function addActive(x){
        if (!x) return false;
        removeActive(x);
        if (currentFocus >= x.length){
        	currentFocus = 0;
        	x[currentFocus].scrollIntoView(true);
        } else if (currentFocus < 0){
        	currentFocus = (x.length - 1);
        	x[currentFocus].scrollIntoView(false);
        }
        x[currentFocus].classList.add("autocomplete-active");
    }

    function removeActive(x){
        for(elem of x){
            elem.classList.remove("autocomplete-active");
        }
    }

    function closeAllLists(){
        let lists = document.getElementsByClassName("autocomplete-values");
        for(list of lists){
            list.parentNode.removeChild(list);
        }
    }
    document.addEventListener("click",closeAllLists,false);
}