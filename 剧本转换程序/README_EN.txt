The author of this player probably put all the text in the sceneData.js file located at ".\package.nw\data\scripts\data\sceneData.js" for faster player response.
The text displayed in the player is all from the sceneData.js file. I assume the principle is to first scan all resource files in scenes, then generate the sceneData.js file.
If you want to display translated text, first translate the script.txt files in the scenes directory, then place scriptConversion.exe in the package.nw directory and double-click to run the program.
This will generate a sceneData.js file in the package.nw directory. Use this file to overwrite the original file at ".\package.nw\data\scripts\data\sceneData.js".
